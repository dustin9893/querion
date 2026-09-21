"""Trợ lý Vận hành đầu cuối: bong bóng, phân quyền cấu hình, trả lời tự nhiên, soạn luồng.

Cần: API đang chạy, worker đã lập chỉ mục kho "Cẩm nang vận hành", provider LLM + embedding bật.
    cd apps/api && .venv/bin/python -m app.seed_ops
    API=https://<domain> ADMIN_PASSWORD=... .venv/bin/python ../../scratch/smoke_ops.py

Luồng sinh ra được **tạo thật rồi chạy thật rồi xoá**, vì "soạn luồng đúng" chỉ có nghĩa khi
luồng đó chạy được, chứ không phải khi nó qua được bộ kiểm.
"""
import json
import os
import sys

import httpx

API = os.environ.get("API", "http://localhost:8000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
c = httpx.Client(base_url=API, timeout=600)

results: list[tuple[str, bool]] = []


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


def answer_of(events: list[dict]) -> str:
    return "".join(e.get("content", "") for e in events if e.get("type") == "token")


# --------------------------------------------------------------------------- đăng nhập
tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": ADMIN_PASSWORD}).json()["access_token"]
SUPER = {"Authorization": f"Bearer {tok}"}
ok("super admin đăng nhập", bool(tok))

unit_admin = c.post("/v1/auth/login", json={"email": "admin.eb@msb-demo.vn", "password": "demo123"})
UNIT = {"Authorization": f"Bearer {unit_admin.json()['access_token']}"} if unit_admin.status_code == 200 else None
ok("quản trị đơn vị đăng nhập (admin.eb)", UNIT is not None, unit_admin.text[:150])

workspaces = c.get("/v1/workspaces", headers=SUPER).json()
ok("đơn vị 'Hệ thống' bị ẩn khỏi bộ chọn đơn vị",
   all(w["name"] != "Hệ thống" for w in workspaces), [w["name"] for w in workspaces])
eb = next((w for w in workspaces if "Doanh nghiệp" in w["name"]), workspaces[0])
SUPER_WS = {**SUPER, "X-Workspace-Id": eb["id"]}

# --------------------------------------------------------------------------- bong bóng
b = c.get("/v1/ops/bubble", headers=SUPER).json()
ok("bong bóng bật cho super admin", b.get("enabled") is True, b)
ok("bong bóng có lời chào", bool(b.get("greeting")), b.get("greeting"))
ok("bong bóng có gợi ý câu hỏi", len(b.get("suggestions") or []) > 0)
ok("bong bóng có danh sách tooltip", len(b.get("tips") or []) > 0)
ok("tooltip có gợi ý gắn theo trang", any(t.get("route") for t in b.get("tips") or []))
ok("nhịp hiện tooltip hợp lệ", (b.get("tip_interval_sec") or 0) >= 60, b.get("tip_interval_sec"))

if UNIT:
    bu = c.get("/v1/ops/bubble", headers=UNIT).json()
    ok("bong bóng cũng hiện cho quản trị đơn vị", bu.get("enabled") is True, bu)

# --------------------------------------------------------------------------- cấu hình: chỉ super admin
cfg = c.get("/v1/ops/config", headers=SUPER)
ok("super admin đọc được cấu hình", cfg.status_code == 200, cfg.text[:200])
cfg = cfg.json()
ok("cấu hình trỏ tới trợ lý hệ thống", bool((cfg.get("assistant") or {}).get("id")), cfg.get("assistant"))
ok("trợ lý chạy trên model riêng", bool((cfg.get("assistant") or {}).get("model")),
   (cfg.get("assistant") or {}).get("model"))

if UNIT:
    ok("quản trị đơn vị KHÔNG đọc được cấu hình (403)",
       c.get("/v1/ops/config", headers=UNIT).status_code == 403)
    ok("quản trị đơn vị KHÔNG ghi được cấu hình (403)",
       c.put("/v1/ops/config", headers=UNIT, json={"enabled": False}).status_code == 403)

bad = c.put("/v1/ops/config", headers=SUPER, json={
    "tips": [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]})
ok("gợi ý trùng id bị chặn (400)", bad.status_code == 400, bad.text[:200])

bad = c.put("/v1/ops/config", headers=SUPER, json={"tip_interval_sec": 5})
ok("nhịp hiện tooltip quá dày bị chặn (400)", bad.status_code == 400, bad.text[:200])

bad = c.put("/v1/ops/config", headers=SUPER, json={"audience_roles": ["staff"]})
ok("vai trò lạ bị chặn (400)", bad.status_code == 400, bad.text[:200])

saved = c.put("/v1/ops/config", headers=SUPER, json={"max_tips_per_session": cfg["max_tips_per_session"]})
ok("lưu cấu hình hợp lệ", saved.status_code == 200, saved.text[:200])

# --------------------------------------------------------------------------- chat hướng dẫn
with c.stream("POST", "/v1/ops/chat", headers=SUPER_WS,
              json={"message": "Vì sao văn bản của tôi lập chỉ mục lỗi và xử lý thế nào?"}) as r:
    ok("chat vận hành trả 200", r.status_code == 200)
    ev = sse(r)

ans = answer_of(ev)
ok("trợ lý trả lời được", len(ans) > 80, ans[:160])
sources = next((e["sources"] for e in ev if e.get("type") == "sources"), [])
# Truy hồi vẫn chạy và nguồn vẫn vào nhật ký để Compliance tra lại được; chỉ giao diện là không
# hiện chip nguồn, vì trợ lý này hướng dẫn dùng phần mềm chứ không tra quy định ngân hàng.
ok("truy hồi vẫn chạy, nguồn vẫn được ghi lại", len(sources) > 0, len(sources))
ok("nguồn lấy từ kho cẩm nang",
   any("Cẩm nang" in (s.get("dataset_name") or "") or "." in (s.get("filename") or "") for s in sources),
   [s.get("filename") for s in sources[:2]])
ok("câu trả lời KHÔNG chèn ký hiệu trích dẫn", "[#" not in ans, ans[:200])
msg_id = next((e["message_id"] for e in ev if e.get("type") == "message_saved"), None)
ok("câu trả lời được lưu lại", bool(msg_id))
conv_id = next((e["conversation_id"] for e in ev if e.get("type") == "conversation_id"), None)

if msg_id:
    fb = c.post(f"/v1/ops/messages/{msg_id}/feedback", headers=SUPER, json={"rating": "up"})
    ok("đánh giá 👍 lưu được", fb.status_code == 200, fb.text[:150])

if conv_id:
    reload_ = c.get(f"/v1/ops/conversations/{conv_id}/messages", headers=SUPER)
    ok("nạp lại được hội thoại", reload_.status_code == 200 and len(reload_.json()) >= 2, reload_.text[:150])
    if UNIT:
        ok("quản trị khác KHÔNG đọc được hội thoại này (404)",
           c.get(f"/v1/ops/conversations/{conv_id}/messages", headers=UNIT).status_code == 404)

runs = c.get("/v1/audit/runs?channel=ops&limit=5", headers=SUPER)
ok("nhật ký nhận kênh 'ops'", runs.status_code == 200 and len(runs.json()) > 0, runs.text[:200])

# --------------------------------------------------------------------------- soạn luồng
with c.stream("POST", "/v1/ops/chat", headers=SUPER_WS, json={
        "message": "Dựng giúp tôi luồng: tra kho tri thức tín dụng rồi soạn prompt và sinh câu trả lời."}) as r:
    ev2 = sse(r)

tool_calls = [e.get("tool") for e in ev2 if e.get("type") == "tool_call"]
ok("trợ lý gọi công cụ soạn luồng", "soan_luong_xu_ly" in tool_calls, tool_calls)
drafts = [e["draft"] for e in ev2 if e.get("type") == "workflow_draft"]
ok("nhận được bản nháp luồng", len(drafts) > 0)

wf_id = None
if drafts:
    d = drafts[-1]
    g = d["graph_json"]
    types = [n["type"] for n in g["nodes"]]
    ok("bản nháp có node đầu vào và kết thúc", types[0] == "input" and types[-1] == "output", types)
    ok("bản nháp có node tra kho", "retrieve" in types, types)
    ok("id kho trong node là id thật",
       all(n["data"].get("dataset_ids") for n in g["nodes"] if n["type"] == "retrieve"))
    pos = [(n["position"]["x"], n["position"]["y"]) for n in g["nodes"]]
    ok("không node nào chồng toạ độ", len(pos) == len(set(pos)))
    ok("bản nháp CHƯA được lưu", d.get("workflow_id") is None, d.get("workflow_id"))

    # người dùng bấm nút: tạo bằng chính quyền của họ
    created = c.post("/v1/workflows", headers=SUPER_WS, json={
        "name": "[smoke_ops] " + d["ten"], "description": d["mo_ta"], "graph_json": g})
    ok("tạo luồng từ bản nháp", created.status_code == 201, created.text[:200])
    if created.status_code == 201:
        wf_id = created.json()["id"]
        run = c.post(f"/v1/workflows/{wf_id}/run", headers=SUPER_WS,
                     json={"query": "Điều kiện giải ngân cho khách hàng doanh nghiệp?"})
        ok("luồng do AI soạn CHẠY ĐƯỢC thật", run.status_code == 200, run.text[:200])
        ok("luồng trả về câu trả lời có nội dung",
           len((run.json().get("answer") or "")) > 60, (run.json().get("answer") or "")[:120])

# --------------------------------------------------------------------------- dọn dẹp
if wf_id:
    c.delete(f"/v1/workflows/{wf_id}", headers=SUPER_WS)
    ok("đã xoá luồng kiểm thử", c.get(f"/v1/workflows/{wf_id}", headers=SUPER_WS).status_code == 404)

passed = sum(1 for _, good in results if good)
print(f"\n===== OPS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
