/**
 * Embedded chat bubble e2e. The mock bank website (demo-site/) is served on two origins:
 *   http://localhost:8090 — allow-listed by seed_demo  → widget must work (customer + staff)
 *   http://localhost:8091 — NOT allow-listed           → browser must refuse to frame /embed
 * Requires the live stack (web :3000, API :8000, worker, providers) + `python -m app.seed_demo`.
 */
import { test, expect, type Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const ALLOWED = "http://localhost:8090";
const BLOCKED = "http://localhost:8091";
const SHOTS = "e2e/screenshots";

async function demoConfig(page: Page) {
  const r = await page.request.get(`${ALLOWED}/config.js`);
  expect(r.ok(), "demo-site/config.js missing — run seed_demo").toBeTruthy();
  const js = await r.text();
  const pick = (k: string) => js.match(new RegExp(`${k}:\\s*\\{\\s*app:\\s*"([^"]+)",\\s*key:\\s*"([^"]+)"`))!;
  const c = pick("customer"), s = pick("staff");
  return { customer: { app: c[1], key: c[2] }, staff: { app: s[1], key: s[2] } };
}

const launcher = (page: Page) => page.locator(".msbka-btn");
const panel = (page: Page) => page.locator(".msbka-panel");
const widget = (page: Page) => page.frameLocator(".msbka-panel iframe");

test.describe.serial("Embedded chat bubble", () => {
  test("customer site: bubble → answer with sources → 👍 → Esc → conversation persists", async ({ page }) => {
    await page.goto(`${ALLOWED}/index.html`);
    await expect(launcher(page)).toBeVisible();
    // loader picked up the widget config (colour from seed = #ee6d1f)
    await expect.poll(async () => launcher(page).evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(238, 109, 31)");
    await expect(launcher(page)).toHaveAttribute("aria-expanded", "false");
    // seeded assistants carry a logo → the launcher shows it instead of the default icon
    await expect(launcher(page).locator("img")).toBeVisible();

    await launcher(page).click();
    await expect(panel(page)).toHaveClass(/msbka-open/);
    await expect(launcher(page)).toHaveAttribute("aria-expanded", "true");

    const w = widget(page);
    await expect(w.getByText("Trợ lý MSB").first()).toBeVisible();
    await expect(w.getByText(/Xin chào! Tôi là trợ lý ảo MSB/)).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/11-embed-customer-open.png` });

    await w.getByRole("button", { name: "Phí chuyển khoản liên ngân hàng trên app?" }).click();
    const bubble = w.locator(".md-body").filter({ hasText: /miễn phí/i }).first();
    await expect(bubble).toBeVisible({ timeout: 120_000 });
    const up = w.getByRole("button", { name: "Hữu ích" }).first();
    await expect(up).toBeVisible();
    await expect(w.getByRole("button", { name: /Nguồn \(\d+\)/ })).toBeVisible();
    await w.getByRole("button", { name: /Nguồn \(\d+\)/ }).click();
    await expect(w.locator("span").filter({ hasText: /^\[#0\]/ }).first()).toContainText("Biểu phí");
    await up.click();
    await expect(w.getByText("Cảm ơn phản hồi của bạn")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/12-embed-customer-answer.png` });

    // Esc closes from the host page
    await page.keyboard.press("Escape");
    await expect(panel(page)).not.toHaveClass(/msbka-open/);
    await expect(launcher(page)).toHaveAttribute("aria-expanded", "false");

    // conversation survives a reload (storage partitioned per embedding site, but present)
    await page.reload();
    await launcher(page).click();
    await expect(widget(page).locator(".md-body").first()).toBeVisible({ timeout: 30_000 });
    await expect(widget(page).getByText(/miễn phí/i).first()).toBeVisible();
  });

  test("intranet: staff assistant asks to log in inside the bubble, then answers with clause citations", async ({ page }) => {
    await page.goto(`${ALLOWED}/intranet.html`);
    await launcher(page).click();
    const w = widget(page);
    await expect(w.getByPlaceholder("Email cán bộ")).toBeVisible();
    await expect(w.getByText("Dành cho cán bộ — đăng nhập để hỏi")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/13-embed-staff-login.png` });

    await w.getByPlaceholder("Email cán bộ").fill("rm.an@msb-demo.vn");
    await w.getByPlaceholder("Mật khẩu").fill("demo123");
    await w.getByRole("button", { name: "Đăng nhập" }).click();
    await expect(w.getByText(/Hỏi tôi về quy trình cấp tín dụng/)).toBeVisible();

    await w.getByRole("button", { name: "Điều kiện giải ngân KHDN có TSBĐ?" }).click();
    await expect(w.locator(".md-body").first()).toBeVisible({ timeout: 120_000 });
    await expect(w.getByRole("button", { name: "Hữu ích" }).first()).toBeVisible();
    await w.getByRole("button", { name: /Nguồn \(\d+\)/ }).click();
    await expect(w.locator("span").filter({ hasText: /Điều \d+/ }).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/14-embed-staff-answer.png` });

    // logout returns to the login form
    await w.getByRole("button", { name: "Đăng xuất" }).click();
    await expect(w.getByPlaceholder("Email cán bộ")).toBeVisible();
  });

  test("non-allow-listed site: browser refuses to frame the widget and the API rejects the origin", async ({ page, request }) => {
    const cfg = await demoConfig(page);
    const cspViolations: string[] = [];
    page.on("console", (m) => { if (/frame-ancestors|Refused to frame|Refused to display/i.test(m.text())) cspViolations.push(m.text()); });

    await page.goto(`${BLOCKED}/index.html`);
    await expect(launcher(page)).toBeVisible();
    await launcher(page).click();
    await page.waitForTimeout(3000);
    // Nothing of ours rendered inside the frame
    await expect(widget(page).getByText(/Gợi ý câu hỏi|Trợ lý MSB/).first()).toHaveCount(0);
    expect(cspViolations.length, "expected a CSP frame-ancestors violation").toBeGreaterThan(0);
    await page.screenshot({ path: `${SHOTS}/15-embed-blocked-origin.png` });

    // Defense in depth: the API also refuses an X-Embed-Origin that is not allow-listed
    const r = await request.post(`${API}/v1/public/assistants/${cfg.customer.app}/chat`, {
      headers: { "X-App-Key": cfg.customer.key, "X-Embed-Origin": BLOCKED }, data: { message: "hi" },
    });
    expect(r.status()).toBe(403);
    // …and the allow-list itself is what the proxy serves as frame-ancestors
    const fa = await (await request.get(`${API}/v1/public/assistants/${cfg.customer.app}/frame-ancestors`)).json();
    expect(fa.allowed_origins).toEqual([ALLOWED]);
    const head = await request.get(`http://localhost:3000/embed/${cfg.customer.app}`);
    expect(head.headers()["content-security-policy"]).toContain(`frame-ancestors 'self' ${ALLOWED}`);
  });

  test("admin: embed tab shows allow-list, snippet and a working preview", async ({ page }) => {
    const cfg = await demoConfig(page);
    await page.goto("http://localhost:3000/login");
    await page.fill("#login-email", "admin@querion.io");
    await page.fill("#login-password", "admin123");
    await page.click("#login-submit");
    await page.waitForURL((u) => !u.pathname.startsWith("/login"));

    // the customer assistant lives in the RB unit → select that workspace first (admin pages are workspace-scoped)
    await page.goto("http://localhost:3000/apps");
    const selector = page.locator("#workspace-selector");
    await expect(selector).toBeVisible();
    if (!(await selector.innerText()).includes("Khối Khách hàng Cá nhân (RB)")) {
      await selector.click();
      await page.getByText("Khối Khách hàng Cá nhân (RB)", { exact: true }).first().click();
      await expect(selector).toContainText("Khối Khách hàng Cá nhân (RB)");
    }
    await page.goto(`http://localhost:3000/apps/${cfg.customer.app}`);
    await page.getByRole("button", { name: /Nhúng vào website/ }).click();
    await expect(page.getByText(ALLOWED, { exact: true })).toBeVisible();
    await expect(page.getByText(/Đang bật — chỉ các website bên dưới nhúng được/)).toBeVisible();
    await expect(page.locator("pre").filter({ hasText: `data-app="${cfg.customer.app}"` })).toBeVisible();
    await expect(page.locator("pre").filter({ hasText: "widget.js" })).toContainText("data-key=");

    // invalid origin is rejected client-side
    await page.getByPlaceholder(/https:\/\/www\.msb\.com\.vn/).fill("msb.com.vn/path");
    await page.getByRole("button", { name: "Thêm", exact: true }).click();
    await expect(page.getByText(/Dạng đúng: https:\/\/ten-mien\.vn/)).toBeVisible();

    // preview iframe renders the same chat panel (our own origin is always an allowed ancestor)
    const preview = page.frameLocator('iframe[title="Preview khung chat"]');
    await expect(preview.getByText("Trợ lý MSB").first()).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: `${SHOTS}/16-admin-embed-tab.png`, fullPage: true });
  });
});
