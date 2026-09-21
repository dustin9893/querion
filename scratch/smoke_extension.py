"""Browser extension là kênh thứ tư của trợ lý cán bộ: phiên đăng nhập mang claim `client`, server
quyết định trợ lý nào được hiện, chat đi vào audit với kênh `extension`.

Cần: API :8000, đã chạy `python -m app.seed_demo`, provider LLM.
Chạy:  apps/api/.venv/bin/python scratch/smoke_extension.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_extension.py
"""
import json
import os
import sys
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=300)
results = []


def ok(label, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, "" if cond else "→ " + str(extra)[:300])
    return bool(cond)


def sse(resp):
    out = []
    for line in resp.iter_lines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            try:
                out.append(json.loads(line[6:]))
            except Exception:
                pass
    return out


def claims(token):
    import base64
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io",
                                     "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
filters = c.get("/v1/audit/filters", headers=A).json()
ws = {w["name"]: w["id"] for w in filters["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
apps = {a["name"]: a for a in filters["apps"]}
tag = uuid.uuid4().hex[:6]

# ---- 1. hai loại phiên: cổng cán bộ và extension
portal = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()
ext = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123", "client": "extension"}).json()
ok("đăng nhập cổng cán bộ: token không mang client extension", claims(portal["access_token"]).get("client") in (None, "portal"))
ok("đăng nhập từ extension: token mang client=extension", claims(ext["access_token"]).get("client") == "extension")
weird = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123", "client": "hacker"}).json()
ok("client lạ bị quy về portal", claims(weird["access_token"]).get("client") in (None, "portal"))
P = {"Authorization": f"Bearer {portal['access_token']}"}
X = {"Authorization": f"Bearer {ext['access_token']}"}

# refresh giữ nguyên surface
r = c.post("/v1/staff/refresh", json={"refresh_token": ext["refresh_token"]}).json()
ok("refresh token của extension trả access token vẫn là extension", claims(r["access_token"]).get("client") == "extension")

# ---- 2. danh sách trợ lý theo surface
portal_apps = {a["name"]: a for g in c.get("/v1/staff/apps", headers=P).json() for a in g["apps"]}
ext_apps = {a["name"]: a for g in c.get("/v1/staff/apps", headers=X).json() for a in g["apps"]}
ok("cổng cán bộ thấy đầy đủ trợ lý (không lọc theo extension)", len(portal_apps) >= len(ext_apps) and "Trợ lý Tín dụng KHDN" in portal_apps,
   (len(portal_apps), len(ext_apps)))
ok("extension chỉ thấy trợ lý đã bật extension_enabled", ext_apps and all(a["extension_enabled"] for a in ext_apps.values()),
   {k: v["extension_enabled"] for k, v in ext_apps.items()})
ok("seed bật extension cho KHDN, Hồ sơ Tín dụng và trợ lý định tuyến",
   {"Trợ lý Tín dụng KHDN", "Trợ lý Hồ sơ Tín dụng", "Trợ lý Tổng hợp (định tuyến)"} <= set(ext_apps), list(ext_apps))
khdn = ext_apps.get("Trợ lý Tín dụng KHDN", {})
ok("KHDN mang extension_hosts để bong bóng chọn mặc định theo trang", bool(khdn.get("extension_hosts")), khdn.get("extension_hosts"))
ok("mỗi trợ lý mang màu chủ đạo cho bong bóng", all("primary_color" in a for a in ext_apps.values()))
not_enabled = [n for n in portal_apps if n not in ext_apps]
ok("có trợ lý cổng cán bộ nhưng không mở cho extension (để kiểm tra 403)", bool(not_enabled), list(portal_apps))

# ---- 3. chat: kênh audit và enforce
target = ext_apps["Trợ lý Tín dụng KHDN"]
with c.stream("POST", f"/v1/staff/apps/{target['id']}/chat", headers={**X, "X-Page-Origin": "http://bpm.msb.local:8443"},
              json={"message": "Điều kiện giải ngân cho khách hàng doanh nghiệp có TSBĐ?"}) as s:
    ev = sse(s)
answer = "".join(e["content"] for e in ev if e["type"] == "token")
saved = next((e for e in ev if e["type"] == "message_saved"), None)
ok("chat từ extension trả lời được", len(answer) > 20 and saved is not None, answer[:120])
if saved:
    run = c.get(f"/v1/audit/runs/{saved['run_id']}", headers=A).json()
    ok("nhật ký ghi kênh 'extension'", run.get("channel") == "extension", run.get("channel"))
    ok("nhật ký ghi trang mà bong bóng đang mở (client_origin)", run.get("client_origin") == "http://bpm.msb.local:8443", run.get("client_origin"))
    ok("nhật ký vẫn ghi đúng cán bộ (asked_by)", "Nguyễn Văn An" in (run.get("asked_by") or ""), run.get("asked_by"))

if not_enabled:
    blocked = portal_apps[not_enabled[0]]
    with c.stream("POST", f"/v1/staff/apps/{blocked['id']}/chat", headers=X, json={"message": "xin chào"}) as s:
        ok("chat từ extension tới trợ lý chưa bật → 403", s.status_code == 403, s.status_code)
    with c.stream("POST", f"/v1/staff/apps/{blocked['id']}/chat", headers=P, json={"message": "xin chào"}) as s:
        ok("cùng trợ lý đó từ cổng cán bộ vẫn chat được", s.status_code == 200, s.status_code)
        sse(s)

# bộ lọc audit biết kênh mới
ok("bộ lọc nhật ký liệt kê kênh extension", "extension" in c.get("/v1/audit/filters", headers=A).json().get("channels", []))
resp = c.get("/v1/audit/runs?channel=extension&days=1", headers=A)
rows = resp.json() if resp.status_code == 200 else []
rows = rows.get("items", rows) if isinstance(rows, dict) else rows
ok("lọc nhật ký theo kênh extension trả danh sách có dòng (không 422)",
   resp.status_code == 200 and isinstance(rows, list) and len(rows) > 0
   and all(r.get("channel") == "extension" for r in rows), (resp.status_code, resp.text[:160]))

# ---- 4. cấu hình trên trợ lý
tmp = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý ext {tag}"}).json()
try:
    r = c.patch(f"/v1/apps/{tmp['id']}", headers=EB, json={"extension_hosts": ["BPM.msb.local/", "*.ttqt.msb.local", "localhost:8092"]})
    ok("tên miền được chuẩn hoá khi lưu", r.status_code == 200 and r.json()["extension_hosts"] == ["bpm.msb.local", "*.ttqt.msb.local", "localhost:8092"], r.text[:200])
    r = c.patch(f"/v1/apps/{tmp['id']}", headers=EB, json={"extension_hosts": ["bpm.msb.local/app"]})
    ok("tên miền có đường dẫn bị chặn (400)", r.status_code == 400, r.status_code)
    r = c.patch(f"/v1/apps/{tmp['id']}", headers=EB, json={"extension_enabled": True})
    ok("bật extension cho trợ lý cán bộ: 200", r.status_code == 200 and r.json()["extension_enabled"] is True, r.text[:160])
    full = c.get(f"/v1/apps/{tmp['id']}", headers=EB).json()
    ok("trả về đủ extension_enabled/extension_hosts", full["extension_enabled"] is True and len(full["extension_hosts"]) == 3)
    # chưa công bố → extension chưa thấy dù đã bật
    ext_now = {a["name"] for g in c.get("/v1/staff/apps", headers=X).json() for a in g["apps"]}
    ok("bật extension nhưng chưa công bố thì extension vẫn chưa thấy", tmp["name"] not in ext_now)
    c.patch(f"/v1/apps/{tmp['id']}", headers=EB, json={"is_published": True})
    ext_now = {a["name"] for g in c.get("/v1/staff/apps", headers=X).json() for a in g["apps"]}
    ok("công bố xong thì extension thấy ngay", tmp["name"] in ext_now, list(ext_now))
finally:
    c.delete(f"/v1/apps/{tmp['id']}", headers=EB)

cust = apps.get("Trợ lý Khách hàng MSB")
if cust:
    H = {**A, "X-Workspace-Id": cust["workspace_id"]}
    r = c.patch(f"/v1/apps/{cust['id']}", headers=H, json={"extension_enabled": True})
    ok("trợ lý khách hàng không bật được extension (400)", r.status_code == 400, r.status_code)

passed = sum(1 for _, v in results if v)
print(f"\n===== EXTENSION: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
