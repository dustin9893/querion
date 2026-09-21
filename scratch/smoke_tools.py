"""Tools: registry theo đơn vị, phân quyền, agent gọi tool, và chốt duyệt thao tác ghi.

Cần: API :8000, mock core :8095 (./scripts/mock-core.sh), provider LLM đang bật.
Chạy:  apps/api/.venv/bin/python scratch/smoke_tools.py
"""
import json
import sys
import os
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
# Địa chỉ API dùng để gọi mock core; chạy với server thì trỏ vào host trong TOOL_INTERNAL_ALLOWLIST.
MOCK = os.environ.get("MOCK_CORE", "http://localhost:8095")
c = httpx.Client(base_url=API, timeout=180)
results = []


def ok(label, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, ("" if cond else "→ ") + str(extra)[:300])
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


# ---------------------------------------------------------------- 0. bối cảnh
try:
    httpx.get(f"{MOCK}/health", timeout=5).raise_for_status()
except Exception:
    print("FAIL mock core chưa chạy → ./scripts/mock-core.sh")
    sys.exit(1)

tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
filters = c.get("/v1/audit/filters", headers=A).json()
ws = {w["name"]: w["id"] for w in filters["workspaces"]}
eb, ops = ws["Khối Khách hàng Doanh nghiệp (EB)"], ws["Khối Vận hành & Thanh toán quốc tế"]
EB = {**A, "X-Workspace-Id": eb}
OPS = {**A, "X-Workspace-Id": ops}
apps_eb = c.get("/v1/apps", headers=EB).json()
credit = next(a for a in apps_eb if a["name"] == "Trợ lý Tín dụng KHDN")

suffix = uuid.uuid4().hex[:6]
created = []

# ---------------------------------------------------------------- 1. CRUD
b = c.get("/v1/tools/builtins", headers=EB).json()
ok("liệt kê công cụ dựng sẵn", any(x["fn"] == "tinh_lich_tra_no" for x in b), [x["fn"] for x in b])

r = c.post("/v1/tools", headers=EB, json={
    "slug": f"lich_tra_no_{suffix}", "name": "Tính lịch trả nợ", "kind": "builtin",
    "description": "Tính lịch trả nợ khoản vay.", "config": {"fn": "tinh_lich_tra_no"}})
ok("tạo công cụ dựng sẵn", r.status_code == 201 and r.json()["params_schema"].get("properties"), r.text[:200])
if r.status_code == 201:
    created.append(("EB", r.json()["id"]))
    t_builtin = r.json()

r = c.post("/v1/tools", headers=EB, json={
    "slug": f"tra_ho_so_{suffix}", "name": "Tra hồ sơ tín dụng", "kind": "http",
    "description": "Tra trạng thái, khách hàng và hạn xử lý của hồ sơ tín dụng theo mã hồ sơ, ví dụ HS2026-0412.",
    "config": {"url": MOCK + "/v1/ho-so/{{ma_ho_so}}", "method": "GET",
               "secret_header": "Authorization", "secret_prefix": "Bearer "},
    "params_schema": {"type": "object", "properties": {"ma_ho_so": {"type": "string", "description": "Mã hồ sơ"}}, "required": ["ma_ho_so"]},
    "secret": "demo-core-token"})
ok("tạo công cụ HTTP có secret", r.status_code == 201 and r.json()["has_secret"] is True, r.text[:200])
t_http = r.json() if r.status_code == 201 else None
if t_http:
    created.append(("EB", t_http["id"]))
blob = json.dumps(t_http, ensure_ascii=False)
ok("secret không bao giờ trả về qua API",
   t_http and "demo-core-token" not in blob and "secret_encrypted" not in blob and t_http["has_secret"] is True,
   {k: v for k, v in (t_http or {}).items() if "secret" in k.lower()})

r = c.post("/v1/tools", headers=EB, json={"slug": f"tra_ho_so_{suffix}", "name": "x", "kind": "builtin",
                                          "description": "x", "config": {"fn": "tinh_lich_tra_no"}})
ok("trùng slug trong cùng đơn vị bị chặn (409)", r.status_code == 409, r.text[:120])
r = c.post("/v1/tools", headers=EB, json={"slug": "sai slug!", "name": "x", "kind": "builtin",
                                          "description": "x", "config": {"fn": "tinh_lich_tra_no"}})
ok("slug sai định dạng bị chặn (400)", r.status_code == 400, r.text[:120])
r = c.post("/v1/tools", headers=EB, json={"slug": f"ssrf_{suffix}", "name": "x", "kind": "http",
                                          "description": "x", "config": {"url": "http://169.254.169.254/latest/meta-data"}})
ok("URL trỏ vào địa chỉ nội bộ bị chặn (400)", r.status_code == 400, r.text[:160])

# ---------------------------------------------------------------- 2. chạy thử
r = c.post(f"/v1/tools/{t_builtin['id']}/test", headers=EB, json={"args": {"so_tien": 2_000_000_000, "lai_suat_nam": 9.5, "so_thang": 24}})
ok("chạy thử công cụ dựng sẵn", r.json().get("ok") and r.json()["result"]["tong_lai"] > 0, r.text[:200])
r = c.post(f"/v1/tools/{t_builtin['id']}/test", headers=EB, json={"args": {"so_tien": -5, "lai_suat_nam": 9.5, "so_thang": 24}})
ok("chạy thử với tham số sai → báo lỗi, không nổ", r.json().get("ok") is False, r.text[:200])
r = c.post(f"/v1/tools/{t_builtin['id']}/test", headers=EB, json={"args": {"a": 1}})
ok("thiếu tham số bắt buộc → thông báo dễ hiểu", r.json().get("ok") is False and "Tham số không hợp lệ" in r.json().get("error", ""), r.text[:200])
r = c.post(f"/v1/tools/{t_http['id']}/test", headers=EB, json={"args": {"ma_ho_so": "HS2026-0412"}})
ok("chạy thử công cụ HTTP lấy được dữ liệu thật", r.json().get("ok") and "STEB05" in r.json()["result"], r.text[:200])

# ---------------------------------------------------------------- 3. phạm vi đơn vị
tools_ops = [t["slug"] for t in c.get("/v1/tools", headers=OPS).json()]
ok("đơn vị khác không thấy công cụ của EB", f"tra_ho_so_{suffix}" not in tools_ops, tools_ops[:6])
r = c.patch(f"/v1/tools/{t_http['id']}", headers=OPS, json={"name": "đổi trộm"})
ok("đơn vị khác không sửa được công cụ của EB (404)", r.status_code == 404, r.text[:120])

apps_ops = c.get("/v1/apps", headers=OPS).json()
ops_app = next(a for a in apps_ops if a["name"] == "Trợ lý Vận hành & TTQT")
r = c.patch(f"/v1/apps/{ops_app['id']}", headers=OPS, json={"tool_ids": [t_http["id"]]})
ok("không gắn được công cụ của đơn vị khác vào trợ lý (400)", r.status_code == 400, r.text[:160])

r = c.patch(f"/v1/tools/{t_builtin['id']}", headers=EB, json={"share_scope": "bank"})
ok("super admin mở công cụ cho toàn ngân hàng", r.status_code == 200 and r.json()["share_scope"] == "bank", r.text[:160])
tools_ops2 = [t["slug"] for t in c.get("/v1/tools", headers=OPS).json()]
ok("sau khi mở, đơn vị khác thấy công cụ dùng chung", f"lich_tra_no_{suffix}" in tools_ops2, tools_ops2[:6])
r = c.patch(f"/v1/apps/{ops_app['id']}", headers=OPS, json={"tool_ids": [t_builtin["id"]]})
ok("gắn được công cụ dùng chung vào trợ lý đơn vị khác", r.status_code == 200, r.text[:160])
r = c.post(f"/v1/tools/{t_builtin['id']}/test", headers=OPS, json={"args": {"so_tien": 100_000_000, "lai_suat_nam": 6, "so_thang": 12}})
ok("chạy thử được công cụ dùng chung từ đơn vị khác", r.status_code == 200 and r.json().get("ok"), r.text[:200])
r = c.post(f"/v1/tools/{t_http['id']}/test", headers=OPS, json={"args": {"ma_ho_so": "HS2026-0412"}})
ok("không chạy thử được công cụ chưa chia sẻ của đơn vị khác (404)", r.status_code == 404, r.text[:120])
r = c.delete(f"/v1/tools/{t_builtin['id']}", headers=OPS)
ok("công cụ dùng chung vẫn không xoá được từ đơn vị khác (404)", r.status_code == 404, r.text[:120])
c.patch(f"/v1/apps/{ops_app['id']}", headers=OPS, json={"tool_ids": []})

# ---------------------------------------------------------------- 4. agent gọi tool (kênh cán bộ)
r = c.patch(f"/v1/apps/{credit['id']}", headers=EB, json={"agent_enabled": True, "tool_ids": [t_builtin["id"], t_http["id"]]})
ok("bật chế độ công cụ cho trợ lý", r.status_code == 200 and r.json()["agent_enabled"] and len(r.json()["tool_ids"]) == 2, r.text[:200])

st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()["access_token"]
S = {"Authorization": f"Bearer {st}"}
with c.stream("POST", f"/v1/staff/apps/{credit['id']}/chat", headers=S,
              json={"message": "Hồ sơ HS2026-0412 đang ở bước nào, hạn xử lý ngày nào?"}) as resp:
    ev = sse(resp)
types = [e["type"] for e in ev]
answer = "".join(e["content"] for e in ev if e["type"] == "token")
ok("agent phát sự kiện gọi công cụ", "tool_call" in types and "tool_result" in types, types)
ok("câu trả lời dùng dữ liệu thật từ công cụ", "STEB05" in answer or "19/09/2026" in answer, answer[:250])
ok("vẫn giữ trích dẫn tài liệu (sources)", "sources" in types, types)

# ---------------------------------------------------------------- 5. chốt duyệt thao tác ghi
r = c.post("/v1/tools", headers=EB, json={
    "slug": f"gia_han_{suffix}", "name": "Gia hạn hồ sơ", "kind": "http", "requires_approval": True,
    "description": "Gia hạn thời gian xử lý hồ sơ tín dụng thêm số ngày chỉ định. Thao tác ghi dữ liệu.",
    "config": {"url": MOCK + "/v1/ho-so/{{ma_ho_so}}/gia-han", "method": "POST", "body": {"so_ngay": "{{so_ngay}}"},
               "secret_header": "Authorization", "secret_prefix": "Bearer "},
    "params_schema": {"type": "object", "properties": {"ma_ho_so": {"type": "string"}, "so_ngay": {"type": "integer"}}, "required": ["ma_ho_so", "so_ngay"]},
    "secret": "demo-core-token"})
t_write = r.json() if r.status_code == 201 else None
ok("tạo công cụ cần duyệt", t_write is not None and t_write["requires_approval"], r.text[:200])
created.append(("EB", t_write["id"]))
c.patch(f"/v1/apps/{credit['id']}", headers=EB, json={"tool_ids": [t_builtin["id"], t_http["id"], t_write["id"]]})

with c.stream("POST", f"/v1/staff/apps/{credit['id']}/chat", headers=S,
              json={"message": "Gia hạn hồ sơ HS2026-0518 thêm 3 ngày giúp tôi."}) as resp:
    ev2 = sse(resp)
appr = next((e for e in ev2 if e["type"] == "tool_approval"), None)
ok("thao tác ghi dừng lại chờ duyệt", appr is not None and appr.get("approval_id"), [e["type"] for e in ev2])
ok("chưa chạy công cụ và chưa trả lời khi chưa duyệt",
   not any(e["type"] == "tool_call" for e in ev2) and not "".join(e.get("content", "") for e in ev2 if e["type"] == "token"),
   [e["type"] for e in ev2])
ok("tham số cần duyệt hiển thị đúng", appr and appr["args"].get("ma_ho_so") == "HS2026-0518" and appr["args"].get("so_ngay") == 3, appr)

runs = c.get("/v1/audit/runs?days=1&limit=20", headers=A).json()
ok("run được đánh dấu chờ duyệt trong nhật ký", any(r_["status"] == "waiting" for r_ in runs), [r_["status"] for r_ in runs[:5]])

# từ chối trước
with c.stream("POST", f"/v1/staff/tool-approvals/{appr['approval_id']}", headers=S, json={"approve": False}) as resp:
    ev3 = sse(resp)
ans3 = "".join(e["content"] for e in ev3 if e["type"] == "token")
ok("từ chối → công cụ không chạy, trợ lý báo lại", any(e["type"] == "tool_result" and e.get("status") == "rejected" for e in ev3), [e["type"] for e in ev3])
before = httpx.get(f"{MOCK}/v1/ho-so/HS2026-0518", headers={"Authorization": "Bearer demo-core-token"}, timeout=10).json()
ok("dữ liệu hệ thống không đổi sau khi từ chối", before["han_xu_ly"] == "18/09/2026", before["han_xu_ly"])

r = c.post(f"/v1/staff/tool-approvals/{appr['approval_id']}", headers=S, json={"approve": True})
ok("không duyệt lại được yêu cầu đã xử lý (404)", r.status_code == 404, r.text[:120])

# rồi duyệt một yêu cầu mới
with c.stream("POST", f"/v1/staff/apps/{credit['id']}/chat", headers=S,
              json={"message": "Gia hạn hồ sơ HS2026-0518 thêm 3 ngày."}) as resp:
    ev4 = sse(resp)
appr2 = next((e for e in ev4 if e["type"] == "tool_approval"), None)
if ok("yêu cầu duyệt thứ hai được tạo", appr2 is not None, [e["type"] for e in ev4]):
    with c.stream("POST", f"/v1/staff/tool-approvals/{appr2['approval_id']}", headers=S, json={"approve": True}) as resp:
        ev5 = sse(resp)
    ans5 = "".join(e["content"] for e in ev5 if e["type"] == "token")
    ok("duyệt → công cụ chạy thật", any(e["type"] == "tool_result" and e.get("status") == "done" for e in ev5), [e["type"] for e in ev5])
    after = httpx.get(f"{MOCK}/v1/ho-so/HS2026-0518", headers={"Authorization": "Bearer demo-core-token"}, timeout=10).json()
    ok("trợ lý báo đúng hạn mới sau khi duyệt", "21/09/2026" in ans5, ans5[:250])
    ok("câu trả lời sau duyệt được lưu (message_saved)", any(e["type"] == "message_saved" for e in ev5), [e["type"] for e in ev5])

steps = None
det_runs = c.get("/v1/audit/runs?days=1&limit=30", headers=A).json()
for r_ in det_runs:
    d = c.get(f"/v1/audit/runs/{r_['id']}", headers=A).json()
    if any(s["node_type"] == "tool_call" for s in d.get("steps", [])):
        steps = d
        break
ok("nhật ký kiểm toán ghi từng lần gọi công cụ", steps is not None, [s["node_type"] for s in (steps or {}).get("steps", [])])

# ---------------------------------------------------------------- 6. kênh khách hàng
cust = next(a for a in c.get("/v1/apps", headers={**A, "X-Workspace-Id": ws["Khối Khách hàng Cá nhân (RB)"]}).json()
            if a["audience"] == "customer" and a["is_published"])
r = c.patch(f"/v1/apps/{cust['id']}", headers={**A, "X-Workspace-Id": ws["Khối Khách hàng Cá nhân (RB)"]},
            json={"tool_ids": [t_builtin["id"]]})
ok("không gắn được công cụ chưa bật cho khách hàng vào trợ lý khách hàng (400)", r.status_code == 400, r.text[:180])

# ---------------------------------------------------------------- dọn dẹp
c.patch(f"/v1/apps/{credit['id']}", headers=EB, json={"agent_enabled": False, "tool_ids": []})
for _, tid in created:
    c.delete(f"/v1/tools/{tid}", headers=EB)
left = [t["slug"] for t in c.get("/v1/tools", headers=EB).json() if suffix in t["slug"]]
ok("dọn dẹp công cụ tạm", not left, left)

passed = sum(1 for _, v in results if v)
print(f"\n===== TOOLS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
