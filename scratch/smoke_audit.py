"""Day-4 smoke: runs are created for staff/customer/admin chats; feedback; audit endpoints + scoping."""
import json, sys
import os
import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=60)

def ok(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label, str(extra)[:220])
    if not cond:
        sys.exit(1)

def sse(resp):
    events = []
    for line in resp.iter_lines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events

# ---- super admin ----
tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
filters = c.get("/v1/audit/filters", headers=A).json()
ok("audit filters", len(filters["workspaces"]) >= 4 and len(filters["apps"]) >= 5, [w["name"] for w in filters["workspaces"]])
staff_app = next(a for a in filters["apps"] if a["name"] == "Trợ lý Tín dụng KHDN")
cust_app = next(a for a in filters["apps"] if a["audience"] == "customer")
eb_ws = staff_app["workspace_id"]

before = c.get("/v1/audit/summary", headers=A).json()["total_runs"]

# ---- staff chat creates a run + message_saved (LLM not configured → failed run, no message) ----
st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()
S = {"Authorization": f"Bearer {st['access_token']}"}
with c.stream("POST", f"/v1/staff/apps/{staff_app['id']}/chat", headers=S, json={"message": "Điều kiện giải ngân KHDN?"}) as r:
    ev = sse(r)
types = [e["type"] for e in ev]
ok("staff SSE envelope", types[0] == "conversation_id" and ("token" in types or "error" in types), types)
has_llm = "token" in types

runs = c.get(f"/v1/audit/runs?channel=staff&app_id={staff_app['id']}&limit=5", headers=A).json()
ok("staff run recorded in audit", len(runs) >= 1 and runs[0]["channel"] == "staff" and runs[0]["asked_by"] == "Nguyễn Văn An"
   and runs[0]["asked_by_meta"] and "MSB01001" in runs[0]["asked_by_meta"] and runs[0]["query_preview"].startswith("Điều kiện"), runs[0] if runs else runs)
run0 = runs[0]
ok("run status reflects LLM availability", run0["status"] == ("completed" if has_llm else "failed"), run0["status"])
detail = c.get(f"/v1/audit/runs/{run0['id']}", headers=A).json()
# Không khẳng định retrieve là bước ĐẦU TIÊN: kỹ năng và bộ nhớ được giải quyết trước khi truy hồi,
# nên chúng đứng trước trong danh sách. Điều cần kiểm là truy hồi CÓ được ghi lại.
ok("run detail has steps (retrieve logged even without LLM)", detail["step_count"] >= 1 and any(s["node_type"] == "retrieve" for s in detail["steps"]), [s["node_type"] for s in detail["steps"]])

# ---- customer chat → run with channel=customer, anonymous ----
key = c.get(f"/v1/apps/{cust_app['id']}", headers={**A, "X-Workspace-Id": cust_app["workspace_id"]}).json()["api_key"]
with c.stream("POST", f"/v1/public/assistants/{cust_app['id']}/chat", headers={"X-App-Key": key}, json={"message": "Phí SMS banking?"}) as r:
    ev2 = sse(r)
cruns = c.get(f"/v1/audit/runs?channel=customer&limit=5", headers=A).json()
ok("customer run recorded, anonymous", len(cruns) >= 1 and cruns[0]["asked_by"].startswith("Khách hàng") and cruns[0]["asked_by_meta"] is None, cruns[0] if cruns else cruns)

# ---- feedback (only possible when an assistant message exists → needs LLM); otherwise test 404 path ----
saved = [e for e in ev if e["type"] == "message_saved"]
if saved:
    fb = c.post(f"/v1/staff/messages/{saved[0]['message_id']}/feedback", headers=S, json={"rating": "down", "reason": "Thiếu trích dẫn Điều cụ thể"})
    ok("staff feedback saved", fb.status_code == 200 and fb.json()["rating"] == "down", fb.text)
    rated = c.get(f"/v1/audit/runs?rating=down&limit=5", headers=A).json()
    ok("audit shows 👎 with reason", any(r["id"] == saved[0]["run_id"] and r["feedback_reason"] for r in rated), rated[:1])
else:
    fb = c.post("/v1/staff/messages/00000000-0000-0000-0000-000000000000/feedback", headers=S, json={"rating": "down"})
    ok("feedback on unknown message → 404 (LLM not configured, skipping positive path)", fb.status_code == 404, fb.text)
bad = c.post("/v1/staff/messages/00000000-0000-0000-0000-000000000000/feedback", headers=S, json={"rating": "meh"})
ok("invalid rating → 400", bad.status_code == 400, bad.text)

# ---- summary ----
summ = c.get("/v1/audit/summary", headers=A).json()
ok("summary counts grew", summ["total_runs"] >= before + 2 and "staff" in summ["runs_by_channel"] and "customer" in summ["runs_by_channel"], summ)

# ---- scoping: EB owner sees EB runs only; RB owner sees no staff-credit runs ----
eb_tok = c.post("/v1/auth/login", json={"email": "admin.eb@msb-demo.vn", "password": "demo123"}).json()["access_token"]
rb_tok = c.post("/v1/auth/login", json={"email": "admin.rb@msb-demo.vn", "password": "demo123"}).json()["access_token"]
eb_runs = c.get("/v1/audit/runs?limit=200", headers={"Authorization": f"Bearer {eb_tok}"}).json()
rb_runs = c.get("/v1/audit/runs?limit=200", headers={"Authorization": f"Bearer {rb_tok}"}).json()
ok("EB owner sees only EB workspace runs", eb_runs and all(r["workspace_id"] == eb_ws for r in eb_runs), {r["workspace_name"] for r in eb_runs})
ok("RB owner does not see EB runs", all(r["workspace_id"] != eb_ws for r in rb_runs), len(rb_runs))
forbidden = c.get(f"/v1/audit/runs/{run0['id']}", headers={"Authorization": f"Bearer {rb_tok}"})
ok("RB owner cannot open EB run detail (404)", forbidden.status_code == 404, forbidden.status_code)

# ---- staff cannot call audit ----
denied = c.get("/v1/audit/runs", headers=S)
ok("staff token rejected on audit (401)", denied.status_code == 401, denied.status_code)

print("ALL PASS" + ("" if has_llm else "  (LLM not configured: token/feedback positive paths skipped)"))
