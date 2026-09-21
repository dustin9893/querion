"""Báo cáo trong chat: hỏi mới chạy (không tự chạy), trả về tệp tải được, và hộp báo cáo của cán bộ
chỉ hiện tệp của chính họ.

Cần: API :8000, mock core :8095, mock DWH :8097, provider LLM.
Chạy:  apps/api/.venv/bin/python scratch/smoke_chat_reports.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_chat_reports.py
"""
import json
import os
import time
import sys
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=300)
results = []
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io",
                                     "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
filters = c.get("/v1/audit/filters", headers=A).json()
ws = {w["name"]: w["id"] for w in filters["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
apps = {a["name"]: a for a in filters["apps"]}
tag = uuid.uuid4().hex[:6]

report_wf = next(w for w in c.get("/v1/workflows", headers=EB).json() if "Excel" in w["name"])

# ---- 1. không cho gắn luồng báo cáo làm bộ não của trợ lý
tmp_app = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý thử {tag}"}).json()
try:
    r = c.patch(f"/v1/apps/{tmp_app['id']}", headers=EB, json={"workflow_id": report_wf["id"]})
    ok("không gắn được luồng báo cáo vào trợ lý (400) và có hướng dẫn dùng công cụ",
       r.status_code == 400 and "công cụ" in r.text.lower(), r.text[:200])
    r2 = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý thử 2 {tag}", "workflow_id": report_wf["id"]})
    ok("tạo mới cũng bị chặn (400)", r2.status_code == 400, r2.status_code)
    if r2.status_code == 201:
        c.delete(f"/v1/apps/{r2.json()['id']}", headers=EB)
finally:
    c.delete(f"/v1/apps/{tmp_app['id']}", headers=EB)

# ---- 2. trợ lý lỡ gắn luồng báo cáo từ trước: chào hỏi vẫn trả lời bình thường
legacy = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý cũ {tag}"}).json()
try:
    with c.stream("POST", f"/v1/apps/{legacy['id']}/test-chat", headers=EB, json={"message": "xin chào"}) as r:
        ev = sse(r)
    answer = "".join(e["content"] for e in ev if e["type"] == "token")
    ok("trợ lý không gắn gì: chào hỏi được trả lời, không có tệp",
       len(answer) > 5 and not any(e["type"] == "artifact" for e in ev), answer[:120])
finally:
    c.delete(f"/v1/apps/{legacy['id']}", headers=EB)

# ---- 3. chat: chào hỏi thì KHÔNG chạy báo cáo
tool_app = apps["Trợ lý Hồ sơ Tín dụng"]
st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()["access_token"]
S = {"Authorization": f"Bearer {st}"}
with c.stream("POST", f"/v1/staff/apps/{tool_app['id']}/chat", headers=S, json={"message": "xin chào"}) as r:
    ev = sse(r)
greeting = "".join(e["content"] for e in ev if e["type"] == "token")
ok("chào hỏi: trả lời như hội thoại, không sinh tệp",
   len(greeting) > 5 and not any(e["type"] == "artifact" for e in ev), greeting[:150])
ok("chào hỏi: không gọi công cụ báo cáo",
   not any(e.get("tool", "").startswith("bao_cao") for e in ev if e["type"] == "tool_call"),
   [e.get("tool") for e in ev if e["type"] == "tool_call"])

# ---- 4. chat: xin báo cáo Excel thì chạy và trả tệp
with c.stream("POST", f"/v1/staff/apps/{tool_app['id']}/chat", headers=S,
              json={"message": "Cho tôi báo cáo kinh doanh tháng 09/2026 bản Excel"}) as r:
    ev = sse(r)
called = [e.get("tool") for e in ev if e["type"] == "tool_call"]
files = [e for e in ev if e["type"] == "artifact"]
ok("xin báo cáo: agent gọi công cụ báo cáo", any("bao_cao" in (t or "") for t in called), called)
ok("chat trả về tệp Excel để tải", any((f.get("content_type") or "").startswith(XLSX_MIME) for f in files),
   [(f.get("filename"), f.get("content_type")) for f in files])
answer = "".join(e["content"] for e in ev if e["type"] == "token")
ok("câu trả lời nhắc tới báo cáo đã lập", len(answer) > 30 and "báo cáo" in answer.lower(), answer[:200])
xlsx = next((f for f in files if (f.get("content_type") or "").startswith(XLSX_MIME)), None)

# ---- 5. cán bộ tải được tệp vừa tạo trong chat
if xlsx:
    dl = c.get(f"/v1/staff/reports/{xlsx['artifact_id']}/download", headers=S)
    ok("cán bộ tải được tệp từ chat", dl.status_code == 200 and dl.content[:2] == b"PK", dl.status_code)

# ---- 6. hộp "Báo cáo của tôi": chỉ tệp của chính cán bộ + tệp lịch gửi cho họ
mine = c.get("/v1/staff/reports", headers=S).json()
ok("tệp vừa tạo nằm trong hộp của cán bộ", xlsx and any(x["id"] == xlsx["artifact_id"] for x in mine),
   [x["title"] for x in mine[:3]])

# một báo cáo do admin chạy tay (không qua lịch) không được hiện cho cán bộ
job = c.post(f"/v1/workflows/{report_wf['id']}/jobs", headers=EB, json={"query": "x", "inputs": {"thang": "09/2026"}}).json()
admin_files = []
for _ in range(60):
    time.sleep(4)
    row = next((x for x in c.get(f"/v1/workflows/{report_wf['id']}/runs", headers=EB).json() if x["id"] == job["run_id"]), {})
    if row.get("status") in ("completed", "failed"):
        admin_files = row.get("artifacts", [])
        break
ok("admin chạy tay: có tạo tệp", len(admin_files) > 0, row.get("status"))
after = c.get("/v1/staff/reports", headers=S).json()
ok("tệp admin chạy tay KHÔNG hiện trong hộp của cán bộ",
   not any(a["id"] in [x["id"] for x in after] for a in admin_files),
   [x["title"] for x in after[:4]])

other = c.post("/v1/staff/login", json={"email": "ca.binh@msb-demo.vn", "password": "demo123"}).json()["access_token"]
other_files = c.get("/v1/staff/reports", headers={"Authorization": f"Bearer {other}"}).json()
ok("cán bộ khác không thấy tệp của người này",
   xlsx and not any(x["id"] == xlsx["artifact_id"] for x in other_files), len(other_files))

# ---- dọn dẹp
for a in admin_files:
    c.delete(f"/v1/artifacts/{a['id']}", headers=EB)
if xlsx:
    c.delete(f"/v1/artifacts/{xlsx['artifact_id']}", headers=EB)
ok("dọn tệp thử", True)

passed = sum(1 for _, v in results if v)
print(f"\n===== CHAT REPORTS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
