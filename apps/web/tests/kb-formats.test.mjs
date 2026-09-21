// Kiểm thử đơn vị cho src/lib/kbFormats.ts — danh sách định dạng tài liệu mà
// knowledge base chấp nhận (thuộc tính accept của ô upload, bỏ đuôi file khi
// hiển thị trích dẫn).
//
// Chạy:  cd apps/web && node --test tests/kb-formats.test.mjs
//
// Không cần cờ nào: Node 24 tự bỏ kiểu TypeScript khi import file .ts
// (type stripping bật mặc định), nên kbFormats.ts không được có import nào.
// Cảnh báo MODULE_TYPELESS_PACKAGE_JSON khi chạy là vô hại (package.json
// không khai báo "type": "module", Node tự nhận ra cú pháp ESM).
// File nằm ở tests/ chứ không phải e2e/ để Playwright không thu thập nó.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { KB_ACCEPT, stripDocExt } from "../src/lib/kbFormats.ts";

test("KB_ACCEPT liệt kê đúng các đuôi file cho ô upload", () => {
  assert.equal(KB_ACCEPT, ".pdf,.docx,.txt,.xlsx");
});

test("stripDocExt bỏ đuôi của các định dạng đã biết, không phân biệt hoa thường", () => {
  assert.equal(stripDocExt("Biểu phí 2026.pdf"), "Biểu phí 2026");
  assert.equal(stripDocExt("quy-trinh.txt"), "quy-trinh");
  assert.equal(stripDocExt("huong-dan.docx"), "huong-dan");
  assert.equal(stripDocExt("SCAN.PDF"), "SCAN");
  assert.equal(stripDocExt("Biểu phí 2026.xlsx"), "Biểu phí 2026");
  assert.equal(stripDocExt("A.XLSX"), "A");
});

test("stripDocExt giữ nguyên tên không kết thúc bằng đuôi đã biết", () => {
  assert.equal(stripDocExt("a.pdf.bak"), "a.pdf.bak");
  assert.equal(stripDocExt("noext"), "noext");
  assert.equal(stripDocExt("a.xlsx.bak"), "a.xlsx.bak");
  // Đuôi phải đứng sau dấu chấm — "notapdf" không phải file .pdf.
  assert.equal(stripDocExt("notapdf"), "notapdf");
  assert.equal(stripDocExt("bangxlsx"), "bangxlsx");
  assert.equal(stripDocExt("pdf"), "pdf");
});

test("stripDocExt chỉ bỏ đuôi cuối cùng", () => {
  assert.equal(stripDocExt("a.txt.pdf"), "a.txt");
});

test("upload.subtitle ở cả hai ngôn ngữ nhắc đủ các định dạng, kể cả XLSX", () => {
  for (const locale of ["vi", "en"]) {
    const url = new URL(`../src/locales/${locale}/datasets.json`, import.meta.url);
    const subtitle = JSON.parse(readFileSync(url, "utf8")).upload.subtitle;
    for (const fmt of [/XLSX/, /PDF/, /DOCX/, /TXT/]) {
      assert.match(subtitle, fmt, `${locale}: ${subtitle}`);
    }
  }
});
