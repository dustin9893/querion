/**
 * Kỹ năng và Bộ nhớ cá nhân trên trình duyệt thật.
 *
 * Chạy với hệ thống đầy đủ (web, API, worker, provider) và dữ liệu của `python -m app.seed_demo`.
 *
 * Năm điều cần chứng minh:
 *   1. Trang kỹ năng liệt kê kỹ năng đã seed kèm điểm chất lượng mô tả
 *   2. Trình soạn chấm mô tả ngay lúc gõ và thử được một câu hỏi thật
 *   3. Trợ lý gắn kỹ năng thì chip kỹ năng hiện dưới câu trả lời của cán bộ
 *   4. Cán bộ thấy và xoá được bộ nhớ của mình tại "Trợ lý nhớ gì về tôi"
 *   5. Trang đó nói rõ những gì trợ lý không bao giờ nhớ
 */
import { test, expect, type Page } from "@playwright/test";

const ADMIN = { email: "admin@querion.io", password: process.env.E2E_ADMIN_PASSWORD || "admin123" };
const RM = { email: "rm.an@msb-demo.vn", password: "demo123" };
const SHOTS = "e2e/screenshots";

async function adminLogin(page: Page) {
  await page.goto("/login");
  await page.fill("#login-email", ADMIN.email);
  await page.fill("#login-password", ADMIN.password);
  await page.click("#login-submit");
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
}

async function staffLogin(page: Page) {
  await page.goto("/staff/login");
  await page.fill("input[type=email]", RM.email);
  await page.fill("input[type=password]", RM.password);
  await page.click("button[type=submit]");
  await page.waitForURL(/\/staff\/chat/, { timeout: 30_000 });
}

test.describe("Kỹ năng", () => {
  test("trang kỹ năng liệt kê kỹ năng đã seed kèm điểm chất lượng", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/skills");

    await expect(page.getByRole("heading", { name: "Kỹ năng" })).toBeVisible();
    await expect(page.getByText("Kiểm tra điều kiện giải ngân")).toBeVisible();
    await expect(page.getByText("kiem-tra-dieu-kien-giai-ngan")).toBeVisible();
    // Mô tả là thứ duy nhất mô hình đọc để quyết định kích hoạt, nên chất lượng của nó hiện ngay
    // trên danh sách chứ không giấu trong trình soạn.
    await expect(page.getByText(/Mô tả: Tốt/).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/skills_list.png`, fullPage: true });
  });

  test("trình soạn chấm mô tả ngay lúc gõ và thử được câu hỏi thật", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/skills");
    await page.getByRole("button", { name: "+ Kỹ năng mới" }).click();

    const desc = page.getByPlaceholder(/Rà soát một hồ sơ tín dụng/);
    await expect(desc).toBeVisible();

    await desc.fill("Giúp giải ngân.");
    await expect(page.getByText(/Cần sửa/)).toBeVisible();

    await desc.fill("Rà soát một hồ sơ tín dụng đã đủ điều kiện giải ngân chưa và còn thiếu gì. "
      + "Dùng khi cán bộ hỏi về giải ngân hoặc chứng từ còn thiếu.");
    await expect(page.getByText(/^Tốt ·/)).toBeVisible();

    // Thử kỹ năng: gõ một câu hỏi thật, xem kỹ năng nào sẽ được kích hoạt.
    await page.getByPlaceholder("Hồ sơ HS2026-0412 đã giải ngân được chưa?")
      .fill("Hồ sơ HS2026-0412 đã giải ngân được chưa?");
    await page.getByRole("button", { name: "Thử", exact: true }).click();
    await expect(page.getByText(/Sẽ kích hoạt|Không kích hoạt kỹ năng nào/)).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: `${SHOTS}/skills_editor.png` });
  });

  test("chip kỹ năng hiện dưới câu trả lời của cán bộ", async ({ page }) => {
    await staffLogin(page);
    await page.getByRole("button", { name: /Trợ lý Tín dụng KHDN/ }).first().click();

    const box = page.getByPlaceholder("Hỏi về quy trình, quy định, sản phẩm...");
    await box.fill("Hồ sơ cho vay từng lần của khách doanh nghiệp đã đủ điều kiện giải ngân chưa?");
    await page.getByRole("button", { name: "Gửi", exact: true }).last().click();

    const chip = page.getByTestId("skill-chip").first();
    await expect(chip).toBeVisible({ timeout: 180_000 });
    await expect(chip).toContainText("Kiểm tra điều kiện giải ngân");
    await page.screenshot({ path: `${SHOTS}/skill_chip.png` });
  });
});

test.describe("Bộ nhớ cá nhân", () => {
  test("cán bộ xem, xoá và hiểu được giới hạn của bộ nhớ", async ({ page }) => {
    await staffLogin(page);

    await page.getByTestId("staff-memory-link").click();
    await page.waitForURL(/\/staff\/memory/, { timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Trợ lý nhớ gì về tôi" })).toBeVisible();

    // Hồ sơ nghề nghiệp do đơn vị quản lý, cán bộ không sửa ở đây — phải nói rõ để khỏi hiểu nhầm.
    await expect(page.getByText("Hồ sơ nghề nghiệp")).toBeVisible();
    await expect(page.getByText(/do đơn vị quản lý/)).toBeVisible();

    // Ranh giới của tính năng phải hiện ngay trên trang, không chỉ nằm trong tài liệu.
    await expect(page.getByText("Trợ lý không bao giờ nhớ")).toBeVisible();
    await expect(page.getByText(/Thông tin khách hàng/)).toBeVisible();
    await expect(page.getByText(/Nội dung quy định/)).toBeVisible();

    // Tạm dừng tách hẳn khỏi xoá sạch: phần lớn người muốn ngừng học thêm chứ không muốn mất hết.
    await expect(page.getByText("Tạm dừng ghi nhớ")).toBeVisible();
    await expect(page.getByRole("button", { name: "Xoá tất cả" })).toBeVisible();

    await page.getByRole("button", { name: "Xoá tất cả" }).click();
    await expect(page.getByRole("button", { name: "Xoá hết" })).toBeVisible();
    await page.getByRole("button", { name: "Huỷ" }).click();

    await page.screenshot({ path: `${SHOTS}/staff_memory.png`, fullPage: true });
  });

  test("trang trợ lý có tab kỹ năng và công tắc bộ nhớ", async ({ page }) => {
    await adminLogin(page);
    await page.goto("/apps");
    await page.getByText("Trợ lý Tín dụng KHDN").first().click();
    await page.waitForURL(/\/apps\/[0-9a-f-]+/, { timeout: 30_000 });

    await page.getByRole("button", { name: /Kỹ năng/ }).click();
    await expect(page.getByTestId("app-skill-list")).toBeVisible();
    await expect(page.getByTestId("memory-state")).toBeVisible();
    await expect(page.getByText(/không bao giờ/)).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/app_skills_tab.png`, fullPage: true });
  });
});
