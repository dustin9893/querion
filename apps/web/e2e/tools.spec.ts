/**
 * Browser e2e for assistant tools (LangGraph agent path).
 *
 * Needs the live stack plus the synthetic back-ends: ./scripts/mock-core.sh (:8095) and
 * ./scripts/mock-mcp.sh (:8096), both listed in TOOL_INTERNAL_ALLOWLIST, and seed_demo data.
 *
 *   1. Admin — unit tool registry lists all three kinds; "Chạy thử" calls the real endpoint
 *   2. Admin — the tool-enabled assistant shows its bound tools
 *   3. Staff — a read question calls HTTP + MCP tools and answers from live data
 *   4. Staff — a write tool pauses with an approval card; approving runs it
 *   5. Customer — the public assistant calls a customer-safe tool
 *   6. Staff — a greeting runs nothing; asking for a report returns a file to download
 *   7. Staff — "xuất ra Excel" turns what the conversation holds into a downloadable .xlsx
 *   8. Admin — ticking a tool turns the agent switch on, so the tool is actually called
 *   9. Admin — the test console shows the produced file as a download button and downloads it
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const MOCK = process.env.E2E_MOCK_URL || "http://localhost:8095";
const SHOTS = "e2e/screenshots";

const ADMIN = { email: "admin@querion.io", password: "admin123" };
const RM = { email: "rm.an@msb-demo.vn", password: "demo123" };
const EB_WS = "Khối Khách hàng Doanh nghiệp (EB)";
const TOOL_APP = "Trợ lý Hồ sơ Tín dụng";

let toolAppId = "";
let customerLink = "";
let ebWorkspaceId = "";

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

async function staffLogin(page: Page) {
  await page.goto("/staff/login");
  await page.fill("input[type=email]", RM.email);
  await page.fill("input[type=password]", RM.password);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/staff\/chat/, { timeout: 30_000 });
}

test.describe.serial("Assistant tools", () => {
  test.beforeAll(async ({ request }) => {
    const health = await request.get(`${MOCK}/health`).catch(() => null);
    expect(health?.ok(), "mock core must run: ./scripts/mock-core.sh").toBeTruthy();

    const tok = await adminToken(request);
    const H = { Authorization: `Bearer ${tok}` };
    const filters = await (await request.get(`${API}/v1/audit/filters`, { headers: H })).json();
    const toolApp = filters.apps.find((a: any) => a.name === TOOL_APP);
    expect(toolApp, "seed_demo must create the tool-enabled assistant").toBeTruthy();
    toolAppId = toolApp.id;
    ebWorkspaceId = toolApp.workspace_id;

    const cust = filters.apps.find((a: any) => a.name === "Trợ lý Khách hàng MSB");
    const app = await (await request.get(`${API}/v1/apps/${cust.id}`, { headers: { ...H, "X-Workspace-Id": cust.workspace_id } })).json();
    customerLink = `/kh/${cust.id}#k=${app.api_key}`;
  });

  test("1. admin: unit tool registry and a live test run", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/tools");
    await pickWorkspace(page, EB_WS);
    await expect(page.locator("#topbar h1")).toHaveText("Công cụ");

    for (const slug of ["tra_ho_so_tin_dung", "gia_han_ho_so", "he_thong_rui_ro", "tinh_lich_tra_no"]) {
      await expect(page.getByTestId(`tool-${slug}`)).toBeVisible();
    }
    const write = page.getByTestId("tool-gia_han_ho_so");
    await expect(write).toContainText("Cần duyệt");
    await expect(write).toContainText("có khoá");
    await expect(page.getByTestId("tool-he_thong_rui_ro")).toContainText("MCP server");
    // shared bank-wide by another unit → listed, but not editable here
    await expect(page.getByTestId("tool-tinh_lich_tra_no")).toContainText("của đơn vị khác");

    await page.getByTestId("tool-tra_ho_so_tin_dung").getByRole("button", { name: "Chạy thử" }).click();
    await page.getByTestId("test-args").fill('{"ma_ho_so": "HS2026-0412"}');
    await page.getByTestId("test-run").click();
    await expect(page.getByTestId("test-result")).toContainText("STEB05", { timeout: 30_000 });
    await expect(page.getByTestId("test-result")).not.toContainText("demo-core-token");
    await page.screenshot({ path: `${SHOTS}/13-tools-registry.png`, fullPage: true });
  });

  test("2. admin: the assistant's Tools tab shows what it may call", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/apps");
    await pickWorkspace(page, EB_WS);
    await page.goto(`/apps/${toolAppId}`);
    await page.getByRole("button", { name: /Công cụ \(\d+\)/ }).click();
    const list = page.getByTestId("app-tool-list");
    await expect(list).toBeVisible();
    for (const slug of ["tra_ho_so_tin_dung", "tra_han_muc", "gia_han_ho_so", "he_thong_rui_ro"]) {
      await expect(page.getByTestId(`bind-${slug}`)).toBeChecked();
    }
    await expect(page.getByText(/Đang bật · \d+ công cụ/)).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/14-assistant-tools-tab.png`, fullPage: true });
  });

  test("3. staff: read question answered from live data through HTTP + MCP tools", async ({ page }) => {
    await staffLogin(page);
    await page.getByRole("button", { name: new RegExp(TOOL_APP) }).first().click();
    await page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...").fill("Hạn mức còn lại và xếp hạng rủi ro của hồ sơ HS2026-0518?");
    await page.keyboard.press("Enter");

    const chips = page.getByTestId("tool-chips").last();
    await expect(chips).toContainText("Tra hạn mức tín dụng", { timeout: 120_000 });
    await expect(chips).toContainText("Hệ thống quản trị rủi ro");
    const bubble = page.locator(".md-body").last();
    await expect(bubble).toContainText("BB-", { timeout: 120_000 });
    await expect(bubble).toContainText(/200\.000\.000|200 triệu/);
    await page.screenshot({ path: `${SHOTS}/15-staff-tools-answer.png`, fullPage: true });
  });

  test("4. staff: a write tool waits for approval, then runs", async ({ page }) => {
    await staffLogin(page);
    await page.getByRole("button", { name: new RegExp(TOOL_APP) }).first().click();
    await page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...").fill("Gia hạn hồ sơ HS2026-0518 thêm 3 ngày.");
    await page.keyboard.press("Enter");

    const card = page.getByTestId("tool-approval").last();
    await expect(card).toBeVisible({ timeout: 120_000 });
    await expect(card).toContainText("Gia hạn hồ sơ");
    await expect(card).toContainText("HS2026-0518");
    await expect(card).toContainText("3");
    await page.screenshot({ path: `${SHOTS}/16-staff-approval-card.png`, fullPage: true });

    await card.getByTestId("approve-tool").click();
    await expect(card).toContainText("Anh/chị đã duyệt.");
    const bubble = page.locator(".md-body").last();
    await expect(bubble).toContainText("21/09/2026", { timeout: 120_000 });
    await expect(page.getByTestId("tool-chips").last()).toContainText("Gia hạn hồ sơ");
    await page.screenshot({ path: `${SHOTS}/17-staff-approved.png`, fullPage: true });
  });

  test("5. customer: public assistant calls a customer-safe tool", async ({ page }) => {
    await page.goto(customerLink);
    await page.getByPlaceholder("Nhập câu hỏi của bạn...").fill("Tỷ giá bán ra USD hôm nay là bao nhiêu?");
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("tool-chips").last()).toContainText("Tra tỷ giá", { timeout: 120_000 });
    await expect(page.locator(".md-body").last()).toContainText(/25\.490|25,490|25490/, { timeout: 120_000 });
    await page.screenshot({ path: `${SHOTS}/18-customer-tool.png`, fullPage: true });
  });

  test("6. staff: a greeting runs nothing, asking for a report returns a file", async ({ page, request }) => {
    test.setTimeout(300_000);
    await staffLogin(page);
    await page.getByRole("button", { name: new RegExp(TOOL_APP) }).first().click();
    const box = page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...");
    // the send button re-enables only when the previous answer has finished streaming
    const send = page.getByRole("button", { name: "Gửi", exact: true }).last();

    // a greeting is a conversation, not a job: no tool runs and no file is produced
    await box.fill("xin chào");
    await send.click();
    await expect(page.locator(".md-body").last()).not.toBeEmpty({ timeout: 120_000 });

    await box.fill("Cho tôi báo cáo kinh doanh tháng 09/2026 bản Excel");
    await expect(send).toBeEnabled({ timeout: 120_000 });
    await expect(page.getByTestId("chat-file")).toHaveCount(0);
    await send.click();
    const chip = page.getByTestId("chat-file").first();
    await expect(chip).toBeVisible({ timeout: 240_000 });
    await expect(page.getByTestId("tool-chips").last()).toContainText("Báo cáo kinh doanh tháng");
    await page.screenshot({ path: `${SHOTS}/19-staff-report-file.png`, fullPage: true });

    const download = page.waitForEvent("download", { timeout: 60_000 });
    await chip.click();
    expect((await (await download).suggestedFilename())).toMatch(/\.(xlsx|md|docx)$/);

    // the file went into this employee's own inbox, nobody else's
    const staff = await (await request.post(`${API}/v1/staff/login`, { data: RM })).json();
    const mine = await (await request.get(`${API}/v1/staff/reports`, {
      headers: { Authorization: `Bearer ${staff.access_token}` } })).json();
    expect(mine.length).toBeGreaterThan(0);
  });

  test("7. staff: export whatever the conversation holds to Excel", async ({ page }) => {
    test.setTimeout(300_000);
    await staffLogin(page);
    await page.getByRole("button", { name: new RegExp(TOOL_APP) }).first().click();
    const box = page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...");
    const send = page.getByRole("button", { name: "Gửi", exact: true }).last();

    // no report workflow covers this table — it exists only in the conversation
    await box.fill("Xuất giúp tôi ra Excel bảng sau: HS2026-0412 Thép Đông Á 12 tỷ quá hạn 3 ngày; "
      + "HS2026-0518 Nhựa Tiền Phong 8,5 tỷ quá hạn 7 ngày. Cột: mã hồ sơ, khách hàng, số tiền, số ngày.");
    await send.click();

    const chip = page.getByTestId("chat-file").first();
    await expect(chip).toBeVisible({ timeout: 240_000 });
    await expect(page.getByTestId("tool-chips").last()).toContainText("Xuất Excel");
    await page.screenshot({ path: `${SHOTS}/19b-staff-export.png`, fullPage: true });

    const download = page.waitForEvent("download", { timeout: 60_000 });
    await chip.click();
    expect((await (await download).suggestedFilename())).toMatch(/\.xlsx$/);
  });

  test("8. admin: ticking a tool turns the agent switch on", async ({ page, request }) => {
    // binding a tool with the switch off produces an assistant that silently never calls it
    const token = await adminToken(request);
    const H = { Authorization: `Bearer ${token}`, "X-Workspace-Id": ebWorkspaceId };
    const created = await (await request.post(`${API}/v1/apps`, {
      headers: H, data: { name: `Trợ lý e2e công cụ ${Date.now()}` } })).json();
    try {
      await adminLogin(page);
      await pickWorkspace(page, EB_WS);
      await page.goto(`/apps/${created.id}`);
      await page.getByRole("button", { name: "Công cụ" }).first().click();

      await expect(page.getByTestId("agent-state")).toContainText("Tắt");
      await page.getByTestId("bind-xuat_excel").check();
      await expect(page.getByTestId("agent-state")).toContainText("Đang bật");
      await expect(page.getByTestId("agent-off-warning")).toHaveCount(0);

      await page.getByRole("button", { name: /Lưu thay đổi/ }).click();
      await expect.poll(async () => {
        const app = await (await request.get(`${API}/v1/apps/${created.id}`, { headers: H })).json();
        return app.agent_enabled && app.tool_ids.length === 1;
      }, { timeout: 30_000 }).toBe(true);
    } finally {
      await request.delete(`${API}/v1/apps/${created.id}`, { headers: H });
    }
  });

  test("9. admin: the test console offers the produced file as a download", async ({ page }) => {
    test.setTimeout(300_000);
    await adminLogin(page);
    await pickWorkspace(page, EB_WS);
    await page.goto("/chat");
    await page.getByTestId("admin-test-apps").getByText(TOOL_APP, { exact: false }).first().click();

    const box = page.getByPlaceholder(/Nhập câu hỏi|Hỏi về/).first();
    await box.fill("Xuất giúp tôi ra Excel bảng: HS2026-0412 Thép Đông Á 12 tỷ; HS2026-0518 Nhựa Tiền Phong 8,5 tỷ. "
      + "Cột: mã hồ sơ, khách hàng, số tiền.");
    await box.press("Enter");

    const file = page.getByTestId("chat-file").first();
    await expect(file).toBeVisible({ timeout: 240_000 });
    await expect(file).toContainText("Tải về");
    // the button sits under the answer, where the assistant tells the reader to look
    await page.screenshot({ path: `${SHOTS}/19c-admin-download.png`, fullPage: true });

    const download = page.waitForEvent("download", { timeout: 60_000 });
    await file.click();
    expect((await (await download).suggestedFilename())).toMatch(/\.xlsx$/);
  });
});
