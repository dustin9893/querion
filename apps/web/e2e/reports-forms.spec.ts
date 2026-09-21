/**
 * Browser e2e for reports, schedules and business forms.
 *
 * Needs the live stack plus: the jobs worker (`python -m app.jobs.worker`), the scheduler
 * (`python -m app.scheduler`), the synthetic core (./scripts/mock-core.sh) and seed_demo data.
 *
 *   1. Admin — run the seeded report in the background, watch it finish, download the file
 *   2. Admin — create a schedule from a preset, run it now, then delete it
 *   3. Staff  — only the scheduled delivery lands in "Báo cáo của tôi", not the admin's manual run
 *   4. Staff  — fill a form: prefill from the core system, AI drafts the free text, export .docx
 *   5. Admin  — the audit log and token page know the new channels
 */
import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const MOCK = process.env.E2E_MOCK_URL || "http://localhost:8095";
const SHOTS = "e2e/screenshots";

const ADMIN = { email: "admin@querion.io", password: "admin123" };
const RM = { email: "rm.an@msb-demo.vn", password: "demo123" };
const EB_WS = "Khối Khách hàng Doanh nghiệp (EB)";
const REPORT_WF = "Báo cáo hồ sơ tín dụng quá hạn SLA";
const FORM_NAME = "Đề nghị giải ngân khoản vay";
const SCHEDULE_NAME = "Lịch e2e";

let reportWorkflowId = "";
let ebWorkspaceId = "";
let token = "";
const createdArtifacts: string[] = [];

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

async function staffToken(request: APIRequestContext) {
  const r = await request.post(`${API}/v1/staff/login`, { data: RM });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token as string;
}

async function staffLogin(page: Page) {
  await page.goto("/staff/login");
  await page.fill("input[type=email]", RM.email);
  await page.fill("input[type=password]", RM.password);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/staff\/chat/, { timeout: 30_000 });
}

test.describe.serial("Reports, schedules and forms", () => {
  test.beforeAll(async ({ request }) => {
    const health = await request.get(`${MOCK}/health`).catch(() => null);
    expect(health?.ok(), "mock core must run: ./scripts/mock-core.sh").toBeTruthy();

    token = await adminToken(request);
    const H = { Authorization: `Bearer ${token}` };
    const workspaces = await (await request.get(`${API}/v1/workspaces`, { headers: H })).json();
    ebWorkspaceId = workspaces.find((w: any) => w.name === EB_WS).id;
    const wfs = await (await request.get(`${API}/v1/workflows`, { headers: { ...H, "X-Workspace-Id": ebWorkspaceId } })).json();
    const report = wfs.find((w: any) => w.name === REPORT_WF);
    expect(report, "seed_demo must create the report workflow").toBeTruthy();
    reportWorkflowId = report.id;
  });

  test.afterAll(async ({ request }) => {
    const H = { Authorization: `Bearer ${token}`, "X-Workspace-Id": ebWorkspaceId };
    for (const id of createdArtifacts) await request.delete(`${API}/v1/artifacts/${id}`, { headers: H });
    const schedules = await (await request.get(`${API}/v1/schedules`, { headers: H })).json();
    for (const s of schedules.filter((x: any) => x.name === SCHEDULE_NAME)) {
      await request.delete(`${API}/v1/schedules/${s.id}`, { headers: H });
    }
  });

  test("1. admin: a report runs in the background and produces downloadable files", async ({ page, request }) => {
    await adminLogin(page);
    await pickWorkspace(page, EB_WS);
    await page.goto(`/workflows/${reportWorkflowId}`);

    await expect(page.getByText("Gọi công cụ").first()).toBeVisible();
    await expect(page.getByText("Xuất tài liệu").first()).toBeVisible();

    const H = { Authorization: `Bearer ${token}`, "X-Workspace-Id": ebWorkspaceId };
    const countArtifacts = async () =>
      (await (await request.get(`${API}/v1/artifacts?workflow_id=${reportWorkflowId}&days=1`, { headers: H })).json()).length;
    const before = await countArtifacts();

    await page.getByTestId("run-open").click();
    // the parameter form is built from the input node's declared fields
    await expect(page.getByTestId("run-input-chi_nhanh")).toBeVisible();
    await page.getByTestId("run-queue").click();

    const panel = page.getByTestId("runs-panel");
    await expect(panel).toBeVisible();
    // this run really produced new files (the panel also lists older runs)
    await expect.poll(countArtifacts, { timeout: 180_000, intervals: [3_000] }).toBeGreaterThan(before);
    await expect(panel.getByTestId("artifact-download").first()).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByText("Hoàn thành").first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/20-report-runs.png`, fullPage: true });

    const download = page.waitForEvent("download", { timeout: 30_000 });
    await panel.getByTestId("artifact-download").first().click();
    expect((await (await download).path())).toBeTruthy();

    const artifacts = await (await request.get(`${API}/v1/artifacts?workflow_id=${reportWorkflowId}&days=1`, { headers: H })).json();
    artifacts.slice(0, 4).forEach((a: any) => createdArtifacts.push(a.id));
  });

  test("2. admin: schedule the report from a preset and run it now", async ({ page }) => {
    test.setTimeout(300_000);   // "Chạy ngay" waits for the report to finish, so test 3 has a delivery
    await adminLogin(page);
    await pickWorkspace(page, EB_WS);
    await page.goto("/admin/schedules");

    await page.getByTestId("new-schedule").click();
    await expect(page.getByTestId("schedule-editor")).toBeVisible();
    await page.getByTestId("schedule-workflow").selectOption({ label: REPORT_WF });
    await page.getByTestId("schedule-name").fill(SCHEDULE_NAME);
    await page.getByTestId("schedule-preset").selectOption("1");   // ngày làm việc
    await page.getByTestId("schedule-time").fill("07:30");
    await expect(page.getByTestId("schedule-cron")).toHaveValue("30 7 * * 1-5");
    // rm.an is an RM: only a delivery addressed to that position reaches their inbox
    await page.getByTestId("schedule-positions").getByRole("button", { name: "RM", exact: true }).click();
    await page.getByTestId("save-schedule").click();

    const card = page.getByTestId("schedule-list").filter({ hasText: SCHEDULE_NAME });
    await expect(card).toBeVisible();
    await expect(card.getByText("07:30 các ngày làm việc (T2–T6)")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/21-schedules.png`, fullPage: true });

    await card.getByTestId("run-now").first().click();
    await expect(card.getByText("Hoàn thành").first()).toBeVisible({ timeout: 180_000 });

    await card.getByTestId("toggle-schedule").first().click();
    await expect(card.getByText("ĐÃ TẮT")).toBeVisible();
  });

  test("3. staff: the scheduled delivery arrives, the admin's manual run does not", async ({ page, request }) => {
    // the inbox is personal: files this employee made, plus what a schedule addressed to their
    // position delivered. The report an admin ran by hand in test 1 must stay out of it.
    const staff = await staffToken(request);
    const inbox = await (await request.get(`${API}/v1/staff/reports`, {
      headers: { Authorization: `Bearer ${staff}` } })).json();
    const inboxIds = inbox.map((a: any) => a.id);
    expect(inboxIds.length, "the schedule delivered to RM in test 2").toBeGreaterThan(0);
    for (const id of createdArtifacts) expect(inboxIds).not.toContain(id);

    await staffLogin(page);
    await page.getByTestId("staff-reports-link").click();
    await page.waitForURL(/\/staff\/reports/);

    await expect(page.getByTestId("staff-reports")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("preview-report").first().click();
    await expect(page.getByTestId("report-preview")).toContainText("HS2026");
    await page.screenshot({ path: `${SHOTS}/22-staff-reports.png`, fullPage: true });

    const download = page.waitForEvent("download", { timeout: 30_000 });
    await page.getByTestId("download-report").first().click();
    expect((await (await download).path())).toBeTruthy();

    inboxIds.forEach((id: string) => createdArtifacts.push(id));
  });

  test("4. staff: fill a form — prefill from the core, AI drafts without seeing PII", async ({ page, request }) => {
    await staffLogin(page);
    await page.getByTestId("staff-forms-link").click();
    await page.waitForURL(/\/staff\/forms/);

    await page.getByTestId("staff-form-list").getByText(FORM_NAME).click();
    await expect(page.getByTestId("form-body")).toBeVisible();
    await expect(page.getByText("không gửi cho AI").first()).toBeVisible();

    await page.getByTestId("prefill-key").fill("HS2026-0412");
    await page.getByTestId("prefill-button").click();
    await expect(page.getByTestId("field-khach_hang")).toHaveValue(/Thép Đông Á/, { timeout: 30_000 });
    await expect(page.getByTestId("field-so_tien")).toHaveValue("12000000000");

    await page.getByTestId("field-so_tien_giai_ngan").fill("4000000000");
    await page.getByTestId("field-muc_dich").fill("Thanh toán tiền mua thép cuộn theo hợp đồng 18/2026");
    await page.getByTestId("field-ngay_de_nghi").fill("18/09/2026");

    await page.getByTestId("suggest-nhan_xet").click();
    await expect(page.getByTestId("field-nhan_xet")).not.toHaveValue("", { timeout: 90_000 });
    // the customer name is PII: it is in the document but must never come back from the model
    expect(await page.getByTestId("field-nhan_xet").inputValue()).not.toContain("Thép Đông Á");
    await page.screenshot({ path: `${SHOTS}/23-staff-form.png`, fullPage: true });

    await page.getByTestId("submit-form").click();
    await expect(page.getByTestId("download-filled")).toBeVisible({ timeout: 60_000 });
    const download = page.waitForEvent("download", { timeout: 30_000 });
    await page.getByTestId("download-filled").click();
    expect((await (await download).suggestedFilename())).toMatch(/\.docx$/);

    const H = { Authorization: `Bearer ${token}`, "X-Workspace-Id": ebWorkspaceId };
    const forms = await (await request.get(`${API}/v1/artifacts?kind=form&days=1`, { headers: H })).json();
    forms.slice(0, 3).forEach((a: any) => createdArtifacts.push(a.id));
  });

  test("5. admin: audit log and token page cover the new channels", async ({ page }) => {
    await adminLogin(page);
    await pickWorkspace(page, EB_WS);

    await page.goto("/admin/audit");
    await page.locator("select").nth(2).selectOption("report");
    await expect(page.getByRole("row").filter({ hasText: "Báo cáo" }).first()).toBeVisible({ timeout: 30_000 });
    await page.locator("select").nth(2).selectOption("form");
    await expect(page.getByRole("row").filter({ hasText: "Biểu mẫu" }).first()).toBeVisible({ timeout: 30_000 });

    await page.goto("/admin/usage");
    await expect(page.getByTestId("usage-by-component")).toContainText("Gợi ý nội dung biểu mẫu", { timeout: 30_000 });
    await expect(page.getByTestId("usage-by-channel")).toContainText("Biểu mẫu");
  });
});
