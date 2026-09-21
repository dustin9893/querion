"""Kỹ năng đầu cuối: chuẩn hoá mã, chấm mô tả, cảnh báo chồng chéo, kích hoạt, xuất nhập SKILL.md.

Cần: API đang chạy, provider embedding + LLM đang bật, đã chạy `python -m app.seed_demo`.
    API=https://<domain> ADMIN_PASSWORD=... .venv/bin/python ../../scratch/smoke_skills.py

Bài quan trọng nhất là "kỹ năng thật sự định hình câu trả lời": kỹ năng qua được bộ kiểm mà không
đổi được cách trợ lý trả lời thì nó chỉ là một dòng trong bảng.
"""
import json
import os
import sys
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
c = httpx.Client(base_url=API, timeout=600)

results: list[tuple[str, bool]] = []
created: list[str] = []


def ok(label: str, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, ("" if cond else "→ " + str(extra)[:300]))
    return bool(cond)


def sse(resp) -> list[dict]:
    out = []
    for line in resp.iter_lines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            try:
                out.append(json.loads(line[6:]))
            except Exception:
                pass
    return out


# --------------------------------------------------------------------------- đăng nhập
tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": ADMIN_PASSWORD}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
ws = c.get("/v1/workspaces", headers=A).json()
eb = next(w for w in ws if "Doanh nghiệp" in w["name"])
H = {**A, "X-Workspace-Id": eb["id"]}
ok("super admin đăng nhập", bool(tok))

# --------------------------------------------------------------------------- danh sách kỹ năng seed
skills = c.get("/v1/skills", headers=H).json()
ok("đơn vị EB có kỹ năng đã seed", len(skills) >= 2, [s["slug"] for s in skills])
by_slug = {s["slug"]: s for s in skills}
giai_ngan = by_slug.get("kiem-tra-dieu-kien-giai-ngan")
ok("kỹ năng 'kiểm tra điều kiện giải ngân' đã công bố",
   giai_ngan and giai_ngan["status"] == "published", giai_ngan)
ok("kỹ năng mẫu có mô tả chất lượng tốt",
   giai_ngan and giai_ngan["quality"]["level"] == "tot", giai_ngan and giai_ngan["quality"])
ok("kỹ năng mẫu gắn với văn bản tham chiếu",
   giai_ngan and len(giai_ngan["reference_document_ids"]) > 0)
ok("kỹ năng mẫu có kho ưu tiên",
   giai_ngan and len(giai_ngan["preferred_dataset_ids"]) > 0)
ok("kỹ năng mẫu đang được trợ lý dùng", giai_ngan and giai_ngan["app_count"] > 0)

# --------------------------------------------------------------------------- kiểm theo chuẩn
bad = c.post("/v1/skills", headers=H, json={
    "name": "Mã sai", "description": "x" * 60, "slug": "Ma--Sai"})
ok("mã kỹ năng sai chuẩn bị chặn (400)", bad.status_code == 400, bad.text[:160])

bad = c.post("/v1/skills", headers=H, json={
    "name": "Mô tả ngắn", "description": "Giúp giải ngân.", "slug": f"mo-ta-ngan-{uuid.uuid4().hex[:6]}"})
ok("mô tả quá ngắn vẫn tạo được nhưng bị chấm yếu",
   bad.status_code == 201 and bad.json()["quality"]["level"] == "yeu",
   bad.text[:200])
if bad.status_code == 201:
    created.append(bad.json()["id"])

# --------------------------------------------------------------------------- tạo và cảnh báo chồng chéo
suffix = uuid.uuid4().hex[:6]
r = c.post("/v1/skills", headers=H, json={
    "slug": f"tra-soat-phi-{suffix}",
    "name": "Tra soát phí giao dịch",
    "description": "Rà soát một khoản phí giao dịch bị trừ sai và hướng dẫn cách tra soát. "
                   "Dùng khi cán bộ hỏi về phí bị trừ nhầm, hoàn phí, hoặc khách khiếu nại về phí.",
    "body": "## Khi nào dùng\n\nCán bộ hỏi về phí bị trừ sai.\n\n## Các bước\n\n1. Xác định loại phí.\n2. Tra biểu phí.\n",
    "status": "published",
})
ok("tạo kỹ năng mới", r.status_code == 201, r.text[:200])
new_skill = r.json() if r.status_code == 201 else None
if new_skill:
    created.append(new_skill["id"])
    ok("mã tự sinh đúng chuẩn", new_skill["slug"] == f"tra-soat-phi-{suffix}")
    ok("mô tả được chấm tốt", new_skill["quality"]["level"] == "tot", new_skill["quality"])

dup = c.post("/v1/skills", headers=H, json={
    "slug": f"tra-soat-phi-trung-{suffix}",
    "name": "Tra soát phí giao dịch (bản 2)",
    "description": "Rà soát một khoản phí giao dịch bị trừ sai và hướng dẫn cách tra soát. "
                   "Dùng khi cán bộ hỏi về phí bị trừ nhầm, hoàn phí, hoặc khách khiếu nại về phí.",
    "body": "## Khi nào dùng\n\nTrùng ý với kỹ năng trên.\n",
})
ok("tạo kỹ năng trùng ý được, nhưng có cảnh báo chồng chéo",
   dup.status_code == 201 and len(dup.json().get("overlaps") or []) > 0,
   dup.json().get("overlaps") if dup.status_code == 201 else dup.text[:200])
if dup.status_code == 201:
    created.append(dup.json()["id"])

trung_slug = c.post("/v1/skills", headers=H, json={
    "slug": f"tra-soat-phi-{suffix}", "name": "x", "description": "y" * 60})
ok("trùng mã trong cùng đơn vị bị chặn (409)", trung_slug.status_code == 409, trung_slug.text[:160])

# --------------------------------------------------------------------------- thử kích hoạt
t = c.post("/v1/skills/try", headers=H, json={"query": "Hồ sơ HS2026-0412 đã giải ngân được chưa?"}).json()
ok("câu hỏi nghiệp vụ kích hoạt đúng kỹ năng",
   (t.get("chosen") or {}).get("slug") == "kiem-tra-dieu-kien-giai-ngan", t.get("chosen"))
ok("điểm khớp vượt ngưỡng", t["best_score"] >= t["threshold"], (t["best_score"], t["threshold"]))

t2 = c.post("/v1/skills/try", headers=H, json={"query": "Hôm nay trời đẹp không?"}).json()
ok("câu hỏi vu vơ KHÔNG kích hoạt kỹ năng nào", t2.get("chosen") is None, t2.get("chosen"))
ok("điểm khớp câu vu vơ dưới ngưỡng", t2["best_score"] < t2["threshold"], (t2["best_score"], t2["threshold"]))

# --------------------------------------------------------------------------- xuất nhập theo chuẩn
if giai_ngan:
    md = c.get(f"/v1/skills/{giai_ngan['id']}/export", headers=H)
    text = md.text
    ok("xuất được SKILL.md", md.status_code == 200 and text.startswith("---"), text[:80])
    ok("frontmatter có name đúng chuẩn", f"name: {giai_ngan['slug']}" in text, text[:200])
    ok("frontmatter có description", "description:" in text)
    ok("giữ tên hiển thị tiếng Việt trong metadata", "display-name:" in text)

z = c.get("/v1/skills-export", headers=H)
ok("xuất được zip cả bộ", z.status_code == 200 and z.headers.get("content-type") == "application/zip",
   (z.status_code, z.headers.get("content-type")))

import_slug = f"nhap-tu-chuan-{suffix}"
skill_md = f"""---
name: {import_slug}
description: Kỹ năng nhập từ tệp theo chuẩn mở để kiểm tra vòng xuất nhập. Dùng khi kiểm thử tính năng nhập kỹ năng.
metadata:
  display-name: Kỹ năng nhập thử
  version: v2.0
---

## Khi nào dùng

Chỉ để kiểm thử.
"""
imp = c.post("/v1/skills-import", headers=A | {"X-Workspace-Id": eb["id"]},
             files={"file": ("test-SKILL.md", skill_md.encode(), "text/markdown")})
ok("nhập được SKILL.md", imp.status_code == 200 and import_slug in imp.json().get("created", []),
   imp.text[:250])
imported = next((s for s in c.get("/v1/skills", headers=H).json() if s["slug"] == import_slug), None)
ok("kỹ năng nhập về ở trạng thái nháp", imported and imported["status"] == "draft", imported)
ok("giữ đúng phiên bản trong metadata", imported and imported["version"] == "v2.0", imported)
if imported:
    created.append(imported["id"])
    again = c.post("/v1/skills-import", headers=A | {"X-Workspace-Id": eb["id"]},
                   files={"file": ("test-SKILL.md", skill_md.encode(), "text/markdown")})
    ok("nhập lại thì bỏ qua vì trùng mã", import_slug in again.json().get("skipped", []), again.text[:200])

# --------------------------------------------------------------------------- gắn vào trợ lý
apps = c.get("/v1/apps", headers=H).json()
tin_dung = next((a for a in apps if a["name"] == "Trợ lý Tín dụng KHDN"), None)
ok("tìm thấy trợ lý tín dụng", tin_dung is not None)

if tin_dung and new_skill:
    detail = c.get(f"/v1/apps/{tin_dung['id']}", headers=H).json()
    ok("trợ lý trả về danh sách kỹ năng đã gắn", isinstance(detail.get("skill_ids"), list), detail.get("skill_ids"))
    ok("trợ lý có ngưỡng khớp kỹ năng", isinstance(detail.get("skill_match_threshold"), (int, float)),
       detail.get("skill_match_threshold"))
    before = list(detail.get("skill_ids") or [])
    upd = c.patch(f"/v1/apps/{tin_dung['id']}", headers=H, json={"skill_ids": before + [new_skill["id"]]})
    ok("gắn thêm kỹ năng vào trợ lý", upd.status_code == 200 and new_skill["id"] in upd.json()["skill_ids"],
       upd.text[:200])
    c.patch(f"/v1/apps/{tin_dung['id']}", headers=H, json={"skill_ids": before})

# Trợ lý khách hàng nằm ở đơn vị khác, nên phải hỏi đúng đơn vị của nó chứ không dùng danh sách EB.
khach = next((a for a in c.get("/v1/audit/filters", headers=A).json().get("apps", [])
              if a["name"] == "Trợ lý Khách hàng MSB"), None)
ok("tìm thấy trợ lý khách hàng", khach is not None)
if khach:
    HK = {**A, "X-Workspace-Id": khach["workspace_id"]}
    rb_skills = c.get("/v1/skills", headers=HK).json()
    mo_khach = next((s for s in rb_skills if s["allow_customer"]), None)
    ok("đơn vị bán lẻ có kỹ năng đã mở cho kênh khách hàng", mo_khach is not None,
       [(s["slug"], s["allow_customer"]) for s in rb_skills])
    khong_mo = next((s for s in rb_skills if not s["allow_customer"] and s["status"] == "published"), None)
    if khong_mo:
        bad_bind = c.patch(f"/v1/apps/{khach['id']}", headers=HK, json={"skill_ids": [khong_mo["id"]]})
        ok("trợ lý khách hàng không gắn được kỹ năng chưa mở cho khách (400)",
           bad_bind.status_code == 400, bad_bind.text[:200])
    if mo_khach:
        good_bind = c.patch(f"/v1/apps/{khach['id']}", headers=HK, json={"skill_ids": [mo_khach["id"]]})
        ok("trợ lý khách hàng gắn được kỹ năng đã mở cho khách",
           good_bind.status_code == 200, good_bind.text[:200])

# --------------------------------------------------------------------------- kỹ năng định hình câu trả lời thật
st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()["access_token"]
S = {"Authorization": f"Bearer {st}"}
staff_apps = [a for g in c.get("/v1/staff/apps", headers=S).json() for a in g["apps"]]
app_td = next((a for a in staff_apps if a["name"] == "Trợ lý Tín dụng KHDN"), None)
ok("cán bộ thấy trợ lý tín dụng", app_td is not None)

if app_td:
    with c.stream("POST", f"/v1/staff/apps/{app_td['id']}/chat", headers=S, json={
            "message": "Hồ sơ cho vay từng lần của khách doanh nghiệp đã đủ điều kiện giải ngân chưa?"}) as r:
        ok("chat cán bộ trả 200", r.status_code == 200)
        ev = sse(r)
    skill_ev = next((e["skill"] for e in ev if e.get("type") == "skill"), None)
    ok("câu trả lời phát sự kiện kỹ năng", skill_ev is not None, sorted({e.get("type") for e in ev}))
    ok("đúng kỹ năng giải ngân được kích hoạt",
       skill_ev and skill_ev["slug"] == "kiem-tra-dieu-kien-giai-ngan", skill_ev)
    ok("sự kiện kỹ năng mang phiên bản", skill_ev and skill_ev.get("version"), skill_ev)
    answer = "".join(e.get("content", "") for e in ev if e.get("type") == "token")
    ok("vẫn trả lời có trích dẫn", "[#" in answer, answer[:150])

    runs = c.get("/v1/audit/runs?channel=staff&limit=1", headers=A).json()
    if runs:
        steps = c.get(f"/v1/audit/runs/{runs[0]['id']}", headers=A).json().get("steps", [])
        ok("nhật ký ghi bước kích hoạt kỹ năng",
           any(s.get("node_type") == "skill_activate" for s in steps),
           [s.get("node_type") for s in steps])

# --------------------------------------------------------------------------- nháp không được dùng
if new_skill:
    c.patch(f"/v1/skills/{new_skill['id']}", headers=H, json={"status": "draft"})
    listed = c.get("/v1/skills", headers=H).json()
    still = next((s for s in listed if s["id"] == new_skill["id"]), None)
    ok("chuyển về nháp được", still and still["status"] == "draft", still)

# --------------------------------------------------------------------------- dọn dẹp
for sid in created:
    c.delete(f"/v1/skills/{sid}", headers=H)
gone = {s["id"] for s in c.get("/v1/skills", headers=H).json()}
ok("đã xoá hết kỹ năng kiểm thử", all(sid not in gone for sid in created))

passed = sum(1 for _, good in results if good)
print(f"\n===== SKILLS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
