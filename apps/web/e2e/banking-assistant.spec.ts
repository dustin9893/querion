/**
 * Browser e2e for the banking knowledge assistant. Runs against a live stack
 * (web :3000, API :8000, worker, embedding + LLM providers) with seed_demo data.
 *
 * Personas covered, in order:
 *   1. Super admin — knowledge bases indexed, assistants published, AI settings
 *   2. Bank staff (RM) — RAG answer with clause citations, 👎 feedback with reason
 *   3. Customer — public page, answer from public KB only, 👍 feedback, bad key rejected
 *   4. Compliance — audit log shows the staff question, its 👎 + reason, sources and steps
 *   5. Workflow canvas — routing workflow renders and a Test Run returns an answer with sources
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const SHOTS = "e2e/screenshots";

const ADMIN = { email: "admin@querion.io", password: "admin123" };
const RM = { email: "rm.an@msb-demo.vn", password: "demo123" };
const EB_WS = "Khối Khách hàng Doanh nghiệp (EB)";
const CREDIT_APP = "Trợ lý Tín dụng KHDN";
const ROUTER_WF = "Định tuyến câu hỏi nội bộ";
const STAFF_Q = "Điều kiện giải ngân cho khách hàng doanh nghiệp có tài sản bảo đảm?";
const FEEDBACK_REASON = "UI-E2E: cần nêu rõ Điều 2 khoản 3";

let customerLink = "";
let customerAppId = "";

async function adminToken(request: APIRequestContext) {
  const r = await request.post(`${API}/v1/auth/login`, { data: ADMIN });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

async function adminLogin(page: Page) {
  await page.goto("/login");
  await page.fill("#login-email", ADMIN.email);
  await page.fill("#login-password", ADMIN.password);
  await page.click("#login-submit");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

async function pickWorkspace(page: Page, name: string) {
  const selector = page.locator("#workspace-selector");
  await expect(selector).toBeVisible();
  if ((await selector.innerText()).includes(name)) return;
  await selector.click();
  await page.getByText(name, { exact: true }).first().click();
  await expect(selector).toContainText(name);
}

test.describe.serial("MSB Knowledge Assistant — browser e2e", () => {
  test.beforeAll(async ({ request }) => {
    // Preconditions: providers configured + seeded docs ready (fail fast with a clear message)
    const tok = await adminToken(request);
    const provs = await (await request.get(`${API}/v1/admin/providers`, { headers: { Authorization: `Bearer ${tok}` } })).json();
    const purposes = new Set(provs.filter((p: any) => p.is_active).map((p: any) => p.purpose));
    expect(purposes.has("embedding") && purposes.has("llm"), "active embedding + llm providers required").toBeTruthy();

    const filters = await (await request.get(`${API}/v1/audit/filters`, { headers: { Authorization: `Bearer ${tok}` } })).json();
    const cust = filters.apps.find((a: any) => a.audience === "customer");
    expect(cust, "seeded customer assistant").toBeTruthy();
    customerAppId = cust.id;
    const app = await (await request.get(`${API}/v1/apps/${cust.id}`, {
      headers: { Authorization: `Bearer ${tok}`, "X-Workspace-Id": cust.workspace_id },
    })).json();
    customerLink = `/kh/${cust.id}#k=${app.api_key}`;
  });

  test("1. admin: knowledge bases indexed, assistants published, AI settings", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/datasets");
    await pickWorkspace(page, EB_WS);

    // the topbar repeats the page title as an <h1>, so pin the page's own heading
    await expect(page.getByRole("heading", { name: "Kho tri thức", level: 2 })).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "Quy trình & quy định tín dụng KHDN" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Nội bộ");
    await row.click();

    // dataset detail: 3 documents, all ready, metadata column populated
    await expect(page.getByRole("heading", { name: "Quy trình & quy định tín dụng KHDN" })).toBeVisible();
    const readyBadges = page.getByText("Sẵn sàng", { exact: true });
    await expect(readyBadges).toHaveCount(3, { timeout: 60_000 });
    await expect(page.getByText("Quy trình · v3.2 · HL 01/03/2026")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/01-admin-dataset.png`, fullPage: true });

    // assistants
    await page.goto("/apps");
    const card = page.locator("div.rounded-xl").filter({ hasText: CREDIT_APP }).first();
    await expect(card).toBeVisible();
    await expect(card).toContainText("Đã công bố");
    await expect(card).toContainText("Cán bộ");
    await expect(page.locator("div.rounded-xl").filter({ hasText: "Trợ lý Tổng hợp (định tuyến)" }).first()).toContainText(ROUTER_WF);
    await page.screenshot({ path: `${SHOTS}/02-admin-assistants.png`, fullPage: true });

    // AI settings show both providers with base URL
    await page.goto("/admin/settings");
    await expect(page.getByRole("heading", { name: "Cài đặt AI", level: 2 })).toBeVisible();
    await expect(page.getByText("EMBEDDING", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("LLM", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("openrouter.ai").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/03-admin-ai-settings.png`, fullPage: true });
  });

  test("2. staff RM: RAG answer with clause citations + 👎 feedback", async ({ page }) => {
    await page.goto("/staff/login");
    await expect(page.getByText("MSB Knowledge Assistant").first()).toBeVisible();
    await page.fill("input[type=email]", RM.email);
    await page.fill("input[type=password]", RM.password);
    await page.click("button[type=submit]");
    await page.waitForURL(/\/staff\/chat/, { timeout: 30_000 });

    // sidebar shows the employee + published staff assistants grouped by unit
    await expect(page.getByText("Nguyễn Văn An")).toBeVisible();
    await expect(page.getByText("MSB01001")).toBeVisible();
    await expect(page.getByText("Trợ lý Khách hàng MSB")).toHaveCount(0); // customer assistants are hidden from staff
    // unit scoping: RM belongs to EB → the OPS assistant is hidden, the bank-wide compliance assistant is shown with a badge
    await expect(page.getByTestId("staff-unit")).toHaveText(EB_WS);
    await expect(page.getByText("Trợ lý Vận hành & TTQT")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Trợ lý Tuân thủ/ })).toContainText("Toàn ngân hàng");
    await page.getByRole("button", { name: new RegExp(CREDIT_APP) }).first().click();

    // suggestion chips are the assistant's own widget config (seed: "Điều kiện giải ngân KHDN có TSBĐ?" …), not hardcoded
    await expect(page.getByTestId("staff-suggestions").getByRole("button", { name: "Điều kiện giải ngân KHDN có TSBĐ?" })).toBeVisible();
    await expect(page.getByTestId("staff-greeting")).toContainText(/Chào anh\/chị/);
    // ask by typing (the audit test later looks this question up)
    await page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...").fill(STAFF_Q);
    await page.keyboard.press("Enter");
    await expect(page.locator("text=" + STAFF_Q).first()).toBeVisible();

    // wait until the answer is persisted (thumbs appear) — LLM latency ≈ 3–15 s
    const thumbDown = page.getByTitle("Chưa đúng / thiếu").first();
    await expect(thumbDown).toBeVisible({ timeout: 120_000 });

    const bubble = page.locator(".md-body").first();
    await expect(bubble).toBeVisible();
    const answer = await bubble.innerText();
    expect(answer.length).toBeGreaterThan(80);
    expect(answer).toMatch(/giải ngân/i);
    // [#n] markers are rendered as citation badges, markdown is rendered (no raw ** left)
    await expect(bubble.locator('span[title^="Nguồn [#"]').first()).toBeVisible();
    expect(answer).not.toContain("**");

    // citation chips carry document · effective date · Điều
    await expect(page.getByText("Nguồn trích dẫn").first()).toBeVisible();
    const chip = page.locator("span").filter({ hasText: /^\[#0\]/ }).first();
    await expect(chip).toBeVisible();
    await expect(chip).toContainText(/Hướng dẫn giải ngân|Quy định về tài sản bảo đảm|Quy trình cấp tín dụng/);
    await expect(chip).toContainText("hiệu lực");
    await expect(page.locator("span").filter({ hasText: /Điều \d+/ }).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/04-staff-answer-citations.png`, fullPage: true });

    // 👎 with reason
    await thumbDown.click();
    const reason = page.getByPlaceholder(/Lý do/);
    await expect(reason).toBeVisible();
    await reason.fill(FEEDBACK_REASON);
    await reason.press("Enter");
    await expect(page.getByText("Đã ghi nhận").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/05-staff-feedback.png`, fullPage: true });

    // conversation tab got an auto title
    await expect(page.locator("button.truncate").first()).toBeVisible({ timeout: 60_000 });
  });

  test("3. customer: public page answers from public KB, 👍, bad key rejected", async ({ page }) => {
    await page.goto(customerLink);
    await expect(page.getByRole("heading", { name: "Trợ lý Khách hàng MSB" })).toBeVisible();
    await expect(page.getByText(/không nhập mật khẩu, mã OTP/i)).toBeVisible();

    await page.getByRole("button", { name: "Phí chuyển khoản liên ngân hàng trên app là bao nhiêu?" }).click();
    const up = page.getByRole("button", { name: "Hữu ích" }).first();
    await expect(up).toBeVisible({ timeout: 120_000 });

    const bubble = page.locator(".md-body").filter({ hasText: /miễn phí/i }).first();
    await expect(bubble).toBeVisible();
    // sources only from the public knowledge base
    const chips = page.locator("span").filter({ hasText: /^\[#\d+\]/ });
    expect(await chips.count()).toBeGreaterThan(0);
    for (const t of await chips.allInnerTexts()) expect(t).toMatch(/Biểu phí|Sản phẩm cho vay/);

    await up.click();
    await expect(page.getByText("Cảm ơn phản hồi của bạn")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/06-customer-answer.png`, fullPage: true });

    // wrong key → no assistant
    await page.goto(`/kh/${customerAppId}#k=app-wrong-key`);
    await expect(page.getByText("Không thể mở trợ lý")).toBeVisible();
    await expect(page.getByText(/không tồn tại hoặc chưa được công bố/)).toBeVisible();
  });

  test("4. compliance: audit log shows the staff question, 👎 reason, sources and steps", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/admin/audit");
    await expect(page.getByRole("heading", { name: "Nhật ký truy vấn", level: 2 })).toBeVisible();
    await expect(page.getByText("Lượt hỏi", { exact: true })).toBeVisible();

    // filter 👎 → our RM question is there with the reason
    await page.locator("select").nth(3).selectOption("down");
    const row = page.getByRole("row").filter({ hasText: STAFF_Q.slice(0, 30) }).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText("Cán bộ");
    await expect(row).toContainText("Nguyễn Văn An");
    await expect(row).toContainText("👎");
    await page.screenshot({ path: `${SHOTS}/07-audit-list.png`, fullPage: true });

    await row.click();
    await expect(page.getByText("Chi tiết lượt hỏi")).toBeVisible();
    await expect(page.getByText("Nguyễn Văn An — MSB01001 · RM · CN Hà Nội", { exact: true })).toBeVisible();
    await expect(page.getByText(FEEDBACK_REASON).first()).toBeVisible();
    await expect(page.getByText(/Nguồn trích dẫn \(\d+\)/)).toBeVisible();
    await expect(page.getByText("Tra cứu kho tri thức").first()).toBeVisible();
    await expect(page.getByText("Sinh câu trả lời (LLM)").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/08-audit-detail.png`, fullPage: true });
    await page.getByRole("button", { name: "Đóng" }).click();

    // customer channel present too
    await page.locator("select").nth(3).selectOption("");
    await page.locator("select").nth(2).selectOption("customer");
    await expect(page.getByRole("row").filter({ hasText: "Khách hàng (ẩn danh)" }).first()).toBeVisible();
  });

  test("5. workflow canvas: routing workflow renders and Test Run answers with sources", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/workflows");
    await pickWorkspace(page, EB_WS);
    await page.getByText(ROUTER_WF).first().click();
    await page.waitForURL(/\/workflows\//);

    await expect(page.locator(".react-flow")).toBeVisible();
    await expect(page.getByText("Phân loại ý định").first()).toBeVisible();
    await expect(page.getByText("Tra kho Vận hành & TTQT").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/09-workflow-canvas.png`, fullPage: true });

    await page.getByTestId("run-open").click();
    await page.getByPlaceholder("Nhập câu hỏi thử...").fill("Điện MT103 trường 71A OUR nghĩa là gì?");
    await page.getByTestId("run-now").click();
    await expect(page.getByText(/Sources \(\d+\)/)).toBeVisible({ timeout: 150_000 });
    await expect(page.getByText(/OUR/).first()).toBeVisible();
    await expect(page.locator("pre").filter({ hasText: /"intent":\s*"van_hanh"/ })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/10-workflow-run.png`, fullPage: true });
  });

  test("6. admin test console: try an assistant of the unit, answer with sources, audited as admin test", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/chat");
    await pickWorkspace(page, EB_WS);
    // topbar shows a translated title, never a raw i18n key
    await expect(page.locator("#topbar h1")).toHaveText("Thử nghiệm hỏi đáp");

    const list = page.getByTestId("admin-test-apps");
    await list.getByRole("button", { name: new RegExp(CREDIT_APP) }).click();
    const console = page.getByTestId("admin-test-console");
    await expect(console.getByText(CREDIT_APP).first()).toBeVisible();
    await expect(console.getByTestId("assistant-logo")).toBeVisible(); // seeded logo

    await console.getByPlaceholder("Nhập câu hỏi của bạn...").fill(STAFF_Q);
    await console.getByRole("button", { name: "Gửi" }).click();
    await expect(console.getByRole("button", { name: /Nguồn \(\d+\)/ })).toBeVisible({ timeout: 120_000 });
    await expect(console.locator(".md-body").first()).toContainText(/Điều|giải ngân/i);
    await page.screenshot({ path: `${SHOTS}/12-admin-test-console.png`, fullPage: true });

    // audited with the admin-test channel, asked by the admin
    await page.goto("/admin/audit");
    await expect(page.locator("#topbar h1")).toHaveText("Nhật ký truy vấn");
    const row = page.getByRole("row").filter({ hasText: "Admin thử" }).filter({ hasText: CREDIT_APP }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(ADMIN.email);
  });
});
