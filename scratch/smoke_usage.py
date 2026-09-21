"""Theo dõi token: mỗi thành phần gọi mô hình ghi token_usage, thống kê theo thành phần / kênh / trợ lý /
đơn vị / mô hình, token hiện trên nhật ký truy vấn, và phạm vi xem như nhật ký truy vấn.

Cần: API :8000, worker, provider LLM + embedding, mock core :8095 + MCP :8096 (tool assistant).
Chạy:  apps/api/.venv/bin/python scratch/smoke_usage.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_usage.py   # trên server
"""
import json
import os
import sys
import time
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=240)
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


def run_id_of(events):
    return next((e.get("run_id") for e in events if e.get("type") == "message_saved"), None)


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
filters = c.get("/v1/audit/filters", headers=A).json()
ws = {w["name"]: w["id"] for w in filters["workspaces"]}
apps = {a["name"]: a for a in filters["apps"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
OPS_ID = ws["Khối Vận hành & Thanh toán quốc tế"]
tag = uuid.uuid4().hex[:6]

st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()["access_token"]
S = {"Authorization": f"Bearer {st}"}


def staff_chat(app_name, message):
    with c.stream("POST", f"/v1/staff/apps/{apps[app_name]['id']}/chat", headers=S, json={"message": message}) as r:
        return sse(r)


def usage_of_run(run_id):
    detail = c.get(f"/v1/audit/runs/{run_id}", headers=A).json()
    return {u["key"]: u for u in detail.get("usage", [])}, detail


# ---- 1. RAG answer on the staff portal: query embedding + answer + title, all on one audit run
ev = staff_chat("Trợ lý Tín dụng KHDN", f"Hồ sơ vay doanh nghiệp cần những giấy tờ gì? ({tag})")
rag_run = run_id_of(ev)
usage, detail = usage_of_run(rag_run)
ok("RAG: ghi token cho nhúng câu hỏi + trả lời + đặt tiêu đề", {"query_embedding", "answer", "title"} <= set(usage), list(usage))
ok("RAG: token trả lời có cả đầu vào và đầu ra", usage.get("answer", {}).get("prompt_tokens", 0) > 100
   and usage.get("answer", {}).get("completion_tokens", 0) > 0, usage.get("answer"))
ok("nhật ký truy vấn: chi tiết có tổng token", detail.get("total_tokens", 0) == sum(u["total_tokens"] for u in usage.values()) > 0, detail.get("total_tokens"))
row = next((r for r in c.get("/v1/audit/runs", headers=A, params={"days": 1}).json() if r["id"] == rag_run), {})
ok("nhật ký truy vấn: danh sách có cột token", row.get("total_tokens") == detail.get("total_tokens"), row.get("total_tokens"))
print(f"     (answer estimated={usage.get('answer', {}).get('estimated_calls')}, embedding estimated={usage.get('query_embedding', {}).get('estimated_calls')})")

# ---- 2. tool agent: several model rounds billed as "agent"
ev = staff_chat("Trợ lý Hồ sơ Tín dụng", f"Hạn mức còn lại của hồ sơ HS2026-0518? ({tag})")
usage, _ = usage_of_run(run_id_of(ev))
ok("agent công cụ: ghi token cho từng vòng gọi mô hình (≥2)", usage.get("agent", {}).get("calls", 0) >= 2, usage.get("agent"))

# ---- 3. workflow router: parameter extraction + generation steps
ev = staff_chat("Trợ lý Tổng hợp (định tuyến)", f"Quy trình phê duyệt tín dụng doanh nghiệp gồm các bước nào? ({tag})")
usage, _ = usage_of_run(run_id_of(ev))
ok("luồng xử lý: ghi token bước trích tham số và bước sinh câu trả lời", {"workflow_extract", "workflow_llm"} <= set(usage), list(usage))

# ---- 4. customer page
cust = next(a for a in filters["apps"] if a["audience"] == "customer")
key = c.get(f"/v1/apps/{cust['id']}", headers={**A, "X-Workspace-Id": cust["workspace_id"]}).json()["api_key"]
with c.stream("POST", f"/v1/public/assistants/{cust['id']}/chat", headers={"X-App-Key": key},
              json={"message": f"Phí chuyển tiền trong nước là bao nhiêu? ({tag})"}) as r:
    ev = sse(r)
usage, detail = usage_of_run(run_id_of(ev))
ok("kênh khách hàng: token được ghi và gắn đúng trợ lý", sum(u["total_tokens"] for u in usage.values()) > 0 and detail.get("app_id") == cust["id"], list(usage))

# ---- 5. retrieval test + document indexing
c.post("/v1/retrieval", headers=EB, json={"query": f"điều kiện giải ngân {tag}", "dataset_ids": [
    c.get("/v1/datasets", headers=EB).json()[0]["id"]], "top_k": 3})
ds = c.post("/v1/datasets", headers=EB, json={"name": f"Kho đo token {tag}", "visibility": "internal"}).json()
doc = c.post(f"/v1/datasets/{ds['id']}/documents/upload", headers=EB,
             files={"file": (f"do_token_{tag}.txt", ("Điều 1. Phạm vi áp dụng\n" + "Văn bản giả lập dùng để đo số token khi lập chỉ mục tài liệu, áp dụng cho các đơn vị kinh doanh. " * 30).encode(), "text/plain")}).json()
for _ in range(90):
    if c.get(f"/v1/documents/{doc['id']}", headers=EB).json()["status"] in ("ready", "failed"):
        break
    time.sleep(2)
c.delete(f"/v1/datasets/{ds['id']}", headers=EB)

# ---- 6. summary
time.sleep(1)
s = c.get("/v1/usage/summary", headers=A, params={"days": 1}).json()
comps = {b["key"]: b for b in s["by_component"]}
ok("thống kê: đủ 7 thành phần", set(comps) >= {"answer", "agent", "workflow_llm", "workflow_extract", "title", "query_embedding", "document_embedding"}, list(comps))
ok("thống kê: tổng = cộng theo thành phần", s["totals"]["total_tokens"] == sum(b["total_tokens"] for b in s["by_component"]) > 0, s["totals"])
ok("thống kê: cộng theo ngày khớp tổng", sum(d["total_tokens"] for d in s["by_day"]) == s["totals"]["total_tokens"] and len(s["by_day"]) == 1, s["by_day"])
chans = {b["key"] for b in s["by_channel"]}
ok("thống kê theo kênh: cán bộ, khách hàng, thử truy vấn, lập chỉ mục", {"staff", "customer", "retrieval_test", "indexing"} <= chans, chans)
ok("thống kê theo mô hình tách LLM và embedding", {b["label"] for b in s["by_model"]} >= {"llm", "embedding"}, s["by_model"])
ok("thống kê theo trợ lý có tên", any(b["label"] == "Trợ lý Hồ sơ Tín dụng" for b in s["by_app"]), [b["label"] for b in s["by_app"]])
ok("usage của kho đã xoá vẫn còn (không mất lịch sử)", comps.get("document_embedding", {}).get("total_tokens", 0) > 0, comps.get("document_embedding"))
eb = c.get("/v1/usage/summary", headers=A, params={"days": 1, "workspace_id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}).json()
ok("lọc theo đơn vị", {b["key"] for b in eb["by_workspace"]} == {ws["Khối Khách hàng Doanh nghiệp (EB)"]}, eb["by_workspace"])
ag = c.get("/v1/usage/summary", headers=A, params={"days": 1, "component": "agent"}).json()
ok("lọc theo thành phần", [b["key"] for b in ag["by_component"]] == ["agent"], ag["by_component"])

# ---- 7. access: an admin who owns only OPS sees only OPS; staff tokens are rejected
ops_st = c.post("/v1/staff/login", json={"email": "gdv.cuong@msb-demo.vn", "password": "demo123"}).json()["access_token"]
with c.stream("POST", f"/v1/staff/apps/{apps['Trợ lý Vận hành & TTQT']['id']}/chat", headers={"Authorization": f"Bearer {ops_st}"},
              json={"message": f"Hồ sơ chuyển tiền quốc tế cần kiểm tra những gì? ({tag})"}) as r:
    sse(r)
u = c.post("/v1/users", headers=A, json={"email": f"owner.ops.{tag}@msb-demo.vn", "password": "demo123", "name": "Chủ OPS"}).json()
try:
    c.post(f"/v1/workspaces/{OPS_ID}/members", headers={**A, "X-Workspace-Id": OPS_ID}, json={"user_id": u["id"], "ws_role": "owner"})
    otok = c.post("/v1/auth/login", json={"email": u["email"], "password": "demo123"}).json()["access_token"]
    o = c.get("/v1/usage/summary", headers={"Authorization": f"Bearer {otok}"}, params={"days": 1}).json()
    ok("chủ đơn vị chỉ thấy token của đơn vị mình", {b["key"] for b in o["by_workspace"]} == {OPS_ID} and o["totals"]["total_tokens"] > 0, o["by_workspace"])
finally:
    c.delete(f"/v1/users/{u['id']}", headers=A)
ok("token cán bộ bị từ chối (401)", c.get("/v1/usage/summary", headers=S).status_code == 401)

passed = sum(1 for _, v in results if v)
print(f"\n===== USAGE: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
