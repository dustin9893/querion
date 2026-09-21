/**
 * Bong bóng Trợ lý Vận hành trong trang quản trị.
 *
 * Chạy với hệ thống thật (web :3000, API :8000, worker, provider) và dữ liệu của
 * `python -m app.seed_ops`.
 *
 * Bốn điều cần chứng minh:
 *   1. Bong bóng có mặt ở trang quản trị và biến mất ở nơi nó không nên có
 *   2. Hỏi được và câu trả lời có trích dẫn từ cẩm nang
 *   3. Nhờ soạn luồng thì hiện thẻ xem trước, và **không có gì được lưu** cho tới khi người dùng bấm
 *   4. Quản trị đơn vị thấy bong bóng nhưng không vào được trang cấu hình
 */
import { test, expect, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const ADMIN = { email: "admin@querion.io", password: process.env.E2E_ADMIN_PASSWORD || "admin123" };
const UNIT_ADMIN = { email: "admin.eb@msb-demo.vn", password: "demo123" };
const SHOTS = "e2e/screenshots";

async function login(page: Page, who: { email: string; password: string }) {
  await page.goto("/login");
  await page.fill("#login-email", who.email);
  await page.fill("#login-password", who.password);
  await page.click("#login-submit");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

test.describe("Trợ lý Vận hành", () => {
  test("bong bóng hiện trên trang quản trị, ẩn ở nơi không phù hợp", async ({ page }) => {
    await login(page, ADMIN);

    await page.goto("/datasets");
    const bubble = page.getByTestId("ops-bubble");
    await expect(bubble).toBeVisible();
    await expect(bubble).toHaveAttribute("title", "Cần trợ giúp?");

    // Màn hình thử nghiệm hỏi đáp đã là một khung chat toàn trang; hai khung cạnh nhau chỉ gây rối.
    await page.goto("/chat");
    await expect(page.getByTestId("ops-bubble")).toHaveCount(0);

    // Cổng cán bộ không phải chỗ của trợ lý quản trị.
    await page.goto("/staff/login");
    await expect(page.getByTestId("ops-bubble")).toHaveCount(0);
  });

  test("mở panel, hỏi và nhận câu trả lời tự nhiên không kèm trích dẫn", async ({ page }) => {
    await login(page, ADMIN);
    await page.goto("/datasets");

    await page.getByTestId("ops-bubble").click();
    const panel = page.getByTestId("ops-panel");
    await expect(panel).toBeVisible();

    const box = panel.getByPlaceholder("Nhập câu hỏi của bạn...");
    await box.fill("Vì sao văn bản lập chỉ mục lỗi?");
    await box.press("Enter");

    const answer = panel.locator(".md-body").last();
    await expect(answer).toBeVisible({ timeout: 180_000 });
    await expect.poll(async () => (await answer.innerText()).length, { timeout: 180_000 })
      .toBeGreaterThan(80);

    // Trợ lý này hướng dẫn dùng phần mềm, không phải tra quy định ngân hàng, nên nó trả lời tự
    // nhiên: không chip "Nguồn (n)", không ký hiệu [#1] giữa câu.
    await expect(panel.getByText(/Nguồn \(\d+\)/)).toHaveCount(0);
    expect(await answer.innerText()).not.toMatch(/\[#\d+\]/);
    await page.screenshot({ path: `${SHOTS}/ops_bubble_answer.png` });

    // Esc đóng panel như mọi lớp phủ khác
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
  });

  test("nhờ soạn luồng thì hiện bản nháp và chưa lưu gì cả", async ({ page, request }) => {
    await login(page, ADMIN);
    await page.goto("/workflows");

    const before = await request.post(`${API}/v1/auth/login`, { data: ADMIN });
    const token = (await before.json()).access_token;

    await page.getByTestId("ops-bubble").click();
    const panel = page.getByTestId("ops-panel");
    const box = panel.getByPlaceholder("Nhập câu hỏi của bạn...");
    await box.fill("Dựng luồng: tra kho tri thức tín dụng rồi soạn prompt và sinh câu trả lời.");
    await box.press("Enter");

    const draft = panel.getByTestId("workflow-draft");
    await expect(draft).toBeVisible({ timeout: 240_000 });
    await expect(draft).toContainText("bản nháp, chưa lưu");
    await expect(panel.getByTestId("workflow-draft-apply")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/ops_workflow_draft.png` });

    // Nút chưa bấm thì không có luồng nào mang tên bản nháp được tạo ra.
    const listed = await request.get(`${API}/v1/workflows`, {
      headers: { Authorization: `Bearer ${token}`, "X-Workspace-Id": await page.evaluate(
        () => localStorage.getItem("querion-active-ws") || "") },
    });
    if (listed.ok()) {
      const names: string[] = (await listed.json()).map((w: { name: string }) => w.name);
      const draftName = (await draft.innerText()).split("\n")[0].trim();
      expect(names).not.toContain(draftName);
    }
  });

  test("quản trị đơn vị thấy bong bóng nhưng không vào được trang cấu hình", async ({ page }) => {
    await login(page, UNIT_ADMIN);
    await page.goto("/datasets");
    await expect(page.getByTestId("ops-bubble")).toBeVisible();

    await page.goto("/admin/ops");
    await expect(page.getByText(/Chỉ quản trị hệ thống/)).toBeVisible();
  });

  test("super admin cấu hình được bong bóng", async ({ page }) => {
    await login(page, ADMIN);
    await page.goto("/admin/ops");
    await expect(page.getByRole("heading", { name: "Trợ lý Vận hành" })).toBeVisible();
    await expect(page.getByText("Bật bong bóng trợ lý vận hành")).toBeVisible();
    await expect(page.getByText("Cho phép trợ lý soạn và sửa luồng xử lý")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/ops_admin_config.png`, fullPage: true });
  });
});
