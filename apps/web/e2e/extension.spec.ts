/**
 * Browser extension e2e — the floating staff bubble on a page that has no widget snippet.
 *
 * Needs the live stack, seed_demo data (run with EXTENSION_DEMO_HOSTS=localhost:8092 so the credit
 * assistant is the default on the test page), the extension built (cd apps/extension && npm run
 * build), and a page served on :8092 (playwright.config.ts starts one from e2e/fixtures/intranet).
 *
 *   1. The extension injects a draggable bubble; the page sees no token and no chat DOM
 *   2. Login inside the panel (client=extension), the page rule picks the default assistant
 *   3. Ask → answer with citations; the audit run carries channel=extension + the page origin
 *   4. Switch assistant from the picker; an assistant not opted in is absent
 *   5. Selecting text on the page offers "Hỏi về đoạn này"
 */
import { test, expect, chromium, type BrowserContext, type Frame, type Page } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const EXT = process.env.E2E_EXT_DIR || resolve(__dirname, "../../extension/dist");   // a build pointed at another API
const PAGE = process.env.E2E_INTRANET_URL || "http://localhost:8092/";
const RM = { email: "rm.an@msb-demo.vn", password: "demo123" };
const SHOTS = "e2e/screenshots";

let ctx: BrowserContext;
let page: Page;

async function panelFrame(p: Page): Promise<Frame> {
  await expect.poll(() => p.frames().some((f) => f.url().startsWith("chrome-extension://") && f.url().includes("panel.html")), { timeout: 15_000 }).toBe(true);
  return p.frames().find((f) => f.url().startsWith("chrome-extension://") && f.url().includes("panel.html"))!;
}

async function bubbleXY(p: Page) {
  // the launcher lives in a closed shadow root: find it by hit-testing the host element
  return p.evaluate(() => {
    const host = document.getElementById("msbka-ext-host")!;
    const r = host.getBoundingClientRect();
    for (const [x, y] of [[r.width - 48, r.height - 48], [88, 148]]) {
      if (document.elementFromPoint(x, y)?.id === "msbka-ext-host") return { x, y };
    }
    return null;
  });
}

test.describe.serial("Browser extension bubble", () => {
  test.beforeAll(async () => {
    ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "msbka-ext-")), {
      channel: "chromium", headless: true, viewport: { width: 1400, height: 900 },
      args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
    });
    page = await ctx.newPage();
  });
  test.afterAll(async () => { await ctx?.close(); });

  test("1. the extension draws a draggable bubble on a page without any snippet", async () => {
    await page.goto(PAGE);
    expect(await page.locator('script[src*="widget.js"]').count()).toBe(0);
    await expect(page.locator("#msbka-ext-host")).toHaveCount(1, { timeout: 15_000 });
    const xy = await bubbleXY(page);
    expect(xy, "launcher hit-test").toBeTruthy();

    // drag to the top-left, release, and the bubble is now there
    await page.mouse.move(xy!.x, xy!.y);
    await page.mouse.down();
    for (let i = 1; i <= 10; i++) await page.mouse.move(xy!.x + (88 - xy!.x) * i / 10, xy!.y + (148 - xy!.y) * i / 10);
    await page.mouse.up();
    await expect.poll(() => page.evaluate(() => document.elementFromPoint(88, 148)?.id)).toBe("msbka-ext-host");
    // the page itself has no chrome.* and no token anywhere in its storage
    expect(await page.evaluate(() => typeof (window as any).chrome?.storage)).toBe("undefined");
    expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => /token|msbka/i.test(k)).length)).toBe(0);
  });

  test("2. login inside the panel and the page rule picks the credit assistant", async () => {
    await page.mouse.click(88, 148);
    const frame = await panelFrame(page);
    await frame.locator("input[type=email]").waitFor({ timeout: 20_000 });
    await frame.fill("input[type=email]", RM.email);
    await frame.fill("input[type=password]", RM.password);
    await frame.locator("button[type=submit]").click();
    // localhost:8092 is in the seeded extension_hosts of "Trợ lý Tín dụng KHDN"
    await expect(frame.locator("h1")).toContainText("Trợ lý Tín dụng KHDN", { timeout: 30_000 });
    await page.screenshot({ path: `${SHOTS}/30-extension-chat.png` });
  });

  test("3. an answer with citations, audited as channel=extension from this page", async ({ request }) => {
    const frame = await panelFrame(page);
    const box = frame.getByPlaceholder(/Nhập câu hỏi|Hỏi về/).first();
    await box.fill("Điều kiện giải ngân cho khách hàng doanh nghiệp có TSBĐ?");
    await box.press("Enter");
    await expect(frame.locator(".md-body").last()).not.toBeEmpty({ timeout: 120_000 });
    await expect(frame.getByText(/Nguồn \(\d+\)/)).toBeVisible({ timeout: 60_000 });

    const tok = (await (await request.post(`${API}/v1/auth/login`, { data: { email: "admin@querion.io", password: process.env.E2E_ADMIN_PASSWORD || "admin123" } })).json()).access_token;
    await expect.poll(async () => {
      const r = await (await request.get(`${API}/v1/audit/runs?channel=extension&days=1`, { headers: { Authorization: `Bearer ${tok}` } })).json();
      const rows = Array.isArray(r) ? r : r.items || [];
      return rows.some((x: any) => (x.client_origin || "") === new URL(PAGE).origin);
    }, { timeout: 30_000 }).toBe(true);
    await page.screenshot({ path: `${SHOTS}/31-extension-answer.png` });
  });

  test("4. the picker lists only opted-in assistants and switches", async () => {
    const frame = await panelFrame(page);
    await frame.getByTestId("switch-assistant").click();
    const picker = frame.getByTestId("assistant-picker");
    await expect(picker).toBeVisible();
    await expect(picker.getByText("Trợ lý Hồ sơ Tín dụng")).toBeVisible();
    await expect(picker.getByText("Trợ lý Tổng hợp (định tuyến)")).toBeVisible();
    await expect(picker.getByTestId("default-badge")).toHaveCount(1);
    // "Trợ lý Tuân thủ" is bank-wide and on the portal, but not opted in for the extension
    await expect(picker.getByText("Trợ lý Tuân thủ")).toHaveCount(0);
    await page.screenshot({ path: `${SHOTS}/32-extension-picker.png` });

    await picker.getByText("Trợ lý Hồ sơ Tín dụng").click();
    await expect(frame.locator("h1")).toContainText("Trợ lý Hồ sơ Tín dụng");
  });

  test("5. selecting text on the page offers to ask about it", async () => {
    const frame = await panelFrame(page);
    await page.evaluate(() => {
      const cell = Array.from(document.querySelectorAll("td")).find((td) => td.textContent?.includes("HS2026-0412"))!;
      const range = document.createRange(); range.selectNodeContents(cell);
      const sel = window.getSelection()!; sel.removeAllRanges(); sel.addRange(range);
      document.dispatchEvent(new Event("selectionchange"));
    });
    await expect(frame.getByTestId("selection-chip")).toContainText("HS2026-0412", { timeout: 10_000 });
    await frame.getByTestId("ask-selection").click();
    await expect(frame.getByPlaceholder(/Nhập câu hỏi|Hỏi về/).first()).toHaveValue(/HS2026-0412/);
  });
});
