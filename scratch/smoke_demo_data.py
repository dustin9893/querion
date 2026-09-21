"""Bộ seed chuẩn: mỗi khối có đủ trợ lý, công cụ, báo cáo, biểu mẫu, kỹ năng — và chúng chạy thật.

Khác các bộ smoke theo tính năng, bộ này kiểm **bộ dữ liệu demo** như giám khảo sẽ thấy: số lượng
đúng, phân quyền theo đơn vị đúng, mỗi trợ lý agent gọi được công cụ của khối mình, ba luồng báo cáo
mới xuất Excel có biểu đồ, luồng phân mức sự cố rẽ đúng nhánh, và trợ lý vẽ biểu đồ trong câu trả lời.

Cần: API, jobs worker, ba mock (:8095 :8096 :8097), provider LLM + embedding, văn bản đã lập chỉ mục.
Chạy:  apps/api/.venv/bin/python scratch/smoke_demo_data.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_demo_data.py
"""
import io
import json
import os
import re
import sys
import time

import httpx

API = os.environ.get("API", "http://localhost:8000")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
c = httpx.Client(base_url=API, timeout=300)
results: list[tuple[str, bool]] = []
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ok(label, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, "" if cond else "→ " + str(extra)[:400])
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


def staff(email: str) -> dict:
    tok = c.post("/v1/staff/login", json={"email": email, "password": "demo123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def staff_apps(headers: dict) -> dict:
    return {a["name"]: a for g in c.get("/v1/staff/apps", headers=headers).json() for a in g["apps"]}


def staff_chat(headers: dict, app_id: str, message: str) -> list[dict]:
    with c.stream("POST", f"/v1/staff/apps/{app_id}/chat", headers=headers, json={"message": message}) as r:
        return sse(r)


# --------------------------------------------------------------------------- đăng nhập admin
tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": ADMIN_PASSWORD}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
units = {w["name"]: w for w in c.get("/v1/workspaces", headers=A).json()}
EB = {**A, "X-Workspace-Id": units["Khối Khách hàng Doanh nghiệp (EB)"]["id"]}
RB = {**A, "X-Workspace-Id": units["Khối Khách hàng Cá nhân (RB)"]["id"]}
OPS = {**A, "X-Workspace-Id": units["Khối Vận hành & Thanh toán quốc tế"]["id"]}
LEGAL = {**A, "X-Workspace-Id": units["Khối Pháp chế & Tuân thủ"]["id"]}
BY_UNIT = {"eb": EB, "rb": RB, "ops": OPS, "legal": LEGAL}

# --------------------------------------------------------------------------- 1. số lượng
ok("4 đơn vị nghiệp vụ (đơn vị Hệ thống bị ẩn)", len(units) == 4, list(units))
datasets = [d for h in BY_UNIT.values() for d in c.get("/v1/datasets", headers=h).json()]
ok("5 kho tri thức", len(datasets) == 5, [d["name"] for d in datasets])
doc_rows = []
for key, h in BY_UNIT.items():
    for ds in c.get("/v1/datasets", headers=h).json():
        doc_rows += c.get(f"/v1/datasets/{ds['id']}", headers=h).json().get("documents", [])
ok("30 văn bản mô phỏng", len(doc_rows) == 30, len(doc_rows))
ok("mọi văn bản đã lập chỉ mục (ready)", all(d["status"] == "ready" for d in doc_rows),
   {d["filename"]: d["status"] for d in doc_rows if d["status"] != "ready"})
apps_all = [a for h in BY_UNIT.values() for a in c.get("/v1/apps", headers=h).json()]
ok("12 trợ lý, tất cả đã công bố", len(apps_all) == 12 and all(a["is_published"] for a in apps_all),
   [(a["name"], a["is_published"]) for a in apps_all])
ok("7 trợ lý agent có công cụ (5 khối nghiệp vụ + Hồ sơ Tín dụng + Khách hàng)", sum(1 for a in apps_all if a["agent_enabled"]) == 7, [a["name"] for a in apps_all if a["agent_enabled"]])
tools_all = {(t["workspace_id"], t["slug"]) for h in BY_UNIT.values() for t in c.get("/v1/tools", headers=h).json()}
ok("≥ 25 công cụ (20 nghiệp vụ + 5 báo cáo)", len(tools_all) >= 25, len(tools_all))
wfs = [w for h in BY_UNIT.values() for w in c.get("/v1/workflows", headers=h).json()]
ok("7 luồng: 2 hội thoại + 5 báo cáo", len(wfs) == 7 and sum(1 for w in wfs if w["type"] == "report") == 5,
   [(w["name"], w["type"]) for w in wfs])
# bank-shared rows are listed for every unit and other suites may add temporary rows, so count by id / by seeded name
SEEDED_SCHEDULES = {"Báo cáo kinh doanh tháng — sáng ngày 1", "Hồ sơ quá hạn SLA — thứ Hai hàng tuần",
                    "Giao dịch TTQT — cuối mỗi ngày làm việc", "Khiếu nại giao dịch — ngày 3 hàng tháng",
                    "Huy động & cho vay KHCN — ngày 2 hàng tháng"}
scheds = {s["id"]: s for h in BY_UNIT.values() for s in c.get("/v1/schedules", headers=h).json()}
seeded = [s for s in scheds.values() if s["name"] in SEEDED_SCHEDULES]
ok("5 lịch chạy seed đang bật, có lần chạy kế", len(seeded) == 5 and all(s["enabled"] and s["next_run_at"] for s in seeded),
   [(s["name"], s.get("next_run_at")) for s in scheds.values()])
forms = {f["id"]: f for h in BY_UNIT.values() for f in c.get("/v1/forms", headers=h).json()}
ok("4 biểu mẫu đã công bố (mẫu Pháp chế chia sẻ toàn ngân hàng)", len(forms) == 4 and all(f["is_published"] for f in forms.values()),
   [(f["name"], f["is_published"]) for f in forms.values()])
skills = {s["id"]: s for h in BY_UNIT.values() for s in c.get("/v1/skills", headers=h).json()}
ok("9 kỹ năng đã công bố", len(skills) == 9 and all(s["status"] == "published" for s in skills.values()),
   [(s["slug"], s["status"]) for s in skills.values()])
emps = c.get("/v1/employees", headers=A).json()
emps = emps.get("items", emps) if isinstance(emps, dict) else emps
ok("10 cán bộ, đủ 6 chức danh", len(emps) == 10 and {e["position"] for e in emps} >= {"RM", "CA", "GDV", "OPS", "CCO", "KSV"},
   [(e["email"], e["position"]) for e in emps])

# --------------------------------------------------------------------------- 2. phân quyền theo khối
S_RB = staff("rm.dung@msb-demo.vn")
S_OPS = staff("ops.hoa@msb-demo.vn")
S_KSV = staff("ksv.linh@msb-demo.vn")
S_LEGAL = staff("cco.nam@msb-demo.vn")
rb_apps, ops_apps, legal_apps = staff_apps(S_RB), staff_apps(S_OPS), staff_apps(S_LEGAL)
ok("RM KHCN thấy trợ lý của khối mình + trợ lý toàn ngân hàng, không thấy của EB",
   "Trợ lý Tư vấn KHCN" in rb_apps and "Trợ lý Rà soát AML" in rb_apps and "Trợ lý Sự cố Tuân thủ (phân mức)" in rb_apps
   and "Trợ lý Hồ sơ Tín dụng" not in rb_apps and "Trợ lý Kiểm soát TTQT" not in rb_apps, sorted(rb_apps))
ok("cán bộ Vận hành thấy hai trợ lý agent của khối", "Trợ lý Kiểm soát TTQT" in ops_apps and "Trợ lý Khiếu nại & Tra soát" in ops_apps, sorted(ops_apps))
ok("cán bộ Pháp chế thấy đủ ba trợ lý của khối", {"Trợ lý Tuân thủ", "Trợ lý Rà soát AML", "Trợ lý Sự cố Tuân thủ (phân mức)"} <= set(legal_apps), sorted(legal_apps))

# --------------------------------------------------------------------------- 3. mỗi khối một câu hỏi có công cụ
ev = staff_chat(S_OPS, ops_apps["Trợ lý Kiểm soát TTQT"]["id"], "Điện TTR2026-1162 đang ở đâu, vì sao bị trả về?")
calls = [e for e in ev if e["type"] == "tool_call"]
ans = answer_of(ev)
ok("TTQT: trợ lý gọi tra hành trình điện SWIFT", any(e["tool"] == "tra_dien_swift" for e in calls), [e["tool"] for e in calls])
ok("TTQT: câu trả lời nêu lý do trả về từ hệ thống", "tài khoản" in ans.lower() and ("trả về" in ans.lower() or "hoàn trả" in ans.lower()), ans[:300])

ev = staff_chat(S_OPS, ops_apps["Trợ lý Kiểm soát TTQT"]["id"], "Sàng lọc đối tác Pyong Trading Corporation, quốc gia Triều Tiên")
calls = [e for e in ev if e["type"] == "tool_call"]
ans = answer_of(ev)
ok("TTQT: sàng lọc cấm vận qua MCP hệ thống rủi ro (công cụ bank-wide của EB)",
   any(e["tool"].startswith("he_thong_rui_ro__") for e in calls), [e["tool"] for e in calls])
ok("TTQT: kết luận dừng / chuyển Tuân thủ khi trùng khớp", any(k in ans.lower() for k in ("dừng", "tuân thủ", "trùng")), ans[:300])

ev = staff_chat(S_KSV, ops_apps["Trợ lý Khiếu nại & Tra soát"]["id"], "Phân công khiếu nại KN2026-0305 cho cán bộ MSB01005")
appr = next((e for e in ev if e["type"] == "tool_approval"), None)
ok("Khiếu nại: thao tác phân công bị chặn lại chờ duyệt", appr is not None and appr["tool"] == "phan_cong_khieu_nai", [e["type"] for e in ev])
if appr:
    with c.stream("POST", f"/v1/staff/tool-approvals/{appr['approval_id']}", headers=S_KSV, json={"approve": False}) as r:
        ev2 = sse(r)
    ok("Khiếu nại: từ chối duyệt → công cụ không chạy, trợ lý nói rõ", any(e["type"] == "tool_result" and e["status"] == "rejected" for e in ev2),
       [(e["type"], e.get("status")) for e in ev2][:6])

ev = staff_chat(S_RB, rb_apps["Trợ lý Tư vấn KHCN"]["id"],
                "Khách thu nhập 40 triệu/tháng, đang trả nợ 5 triệu/tháng, muốn vay 1,5 tỷ trong 20 năm lãi 9,5%. DTI có đạt không?")
calls = [e for e in ev if e["type"] == "tool_call"]
ans = answer_of(ev)
ok("KHCN: trợ lý tính bằng công cụ (DTI hoặc lịch trả nợ), không đoán số",
   any(e["tool"] in ("kiem_tra_kha_nang_tra_no", "tinh_lich_tra_no") for e in calls), [e["tool"] for e in calls])
ok("KHCN: trả lời có DTI và ngưỡng 70%", "70" in ans and "dti" in ans.lower(), ans[:300])

# skill activation on a RAG assistant is server-side (cosine preselect), so it is deterministic enough to assert
ev = staff_chat(S_LEGAL, legal_apps["Trợ lý Tuân thủ"]["id"],
                "Khách hàng nộp tiền mặt 380 triệu rồi 390 triệu trong cùng ngày ở hai phòng giao dịch, có dấu hiệu đáng ngờ và phải báo cáo không?")
ans = answer_of(ev)
ok("Tuân thủ: kỹ năng đánh giá giao dịch đáng ngờ được chọn tự động",
   any(e["type"] == "skill" and "danh-gia-giao-dich-dang-ngo" in json.dumps(e) for e in ev), [e for e in ev if e["type"] == "skill"])
ok("Tuân thủ: nêu ngưỡng 400 triệu có trích dẫn", "400" in ans and re.search(r"\[#\d+", ans), ans[:300])

# --------------------------------------------------------------------------- 4. biểu đồ trong câu trả lời
ev = staff_chat(S_RB, rb_apps["Trợ lý Tư vấn KHCN"]["id"], "Lãi suất tiết kiệm theo từng kỳ hạn hiện nay? Vẽ biểu đồ cột.")
ans = answer_of(ev)
m = re.search(r"```chart\s*(\{.*?\})\s*```", ans, re.S)
spec = None
if m:
    try:
        spec = json.loads(m.group(1))
    except Exception:
        spec = None
ok("biểu đồ: câu trả lời có khối ```chart JSON hợp lệ", spec is not None, ans[-400:])
ok("biểu đồ: đúng cấu trúc loai / nhan / chuoi với số thuần",
   spec is not None and spec.get("loai") in ("cot", "cot_ngang", "duong", "tron") and isinstance(spec.get("nhan"), list)
   and spec.get("chuoi") and all(isinstance(v, (int, float)) for v in spec["chuoi"][0].get("gia_tri", [])), spec)
saved = next((e for e in ev if e["type"] == "message_saved"), None)
if saved:
    detail = c.get(f"/v1/audit/runs/{saved['run_id']}", headers=A).json()
    ok("biểu đồ: nằm trong câu trả lời đã lưu, Compliance mở lại thấy", "```chart" in (detail.get("answer") or ""), list(detail)[:8])

# khách hàng không nhận hướng dẫn vẽ biểu đồ, nhưng gọi được lãi suất
cust = next(a for a in apps_all if a["audience"] == "customer")
K = {"X-App-Key": cust["api_key"]}
with c.stream("POST", f"/v1/public/assistants/{cust['id']}/chat", headers=K, json={"message": "Lãi suất tiết kiệm 12 tháng hiện là bao nhiêu?"}) as r:
    ev = sse(r)
ans = answer_of(ev)
# the public knowledge base now holds a reference rate table too, so the model may answer from the
# document (with a citation) or from the tool — both are right; what must not happen is a bare guess
ok("khách hàng: lãi suất lấy từ công cụ (allow_customer) hoặc từ cẩm nang có trích dẫn",
   any(e["type"] == "tool_call" and e["tool"] == "tra_lai_suat" for e in ev) or (re.search(r"\[#\d+\]", ans) and any(e["type"] == "sources" and e["sources"] for e in ev)),
   [e["tool"] for e in ev if e["type"] == "tool_call"])
ok("khách hàng: nêu đúng mức 5,3%/năm và không vẽ biểu đồ", ("5,3" in ans or "5.3" in ans) and "```chart" not in ans, ans[:300])

# --------------------------------------------------------------------------- 5. luồng phân mức sự cố
incident = legal_apps["Trợ lý Sự cố Tuân thủ (phân mức)"]
ev = staff_chat(S_LEGAL, incident["id"], "Tôi vừa gửi nhầm file danh sách khách hàng kèm số CCCD ra một địa chỉ email bên ngoài ngân hàng, giờ phải làm gì?")
ans = answer_of(ev)
ok("sự cố khẩn: rẽ nhánh khẩn, câu trả lời mở đầu bằng cảnh báo và các bước làm ngay",
   "⚠️" in ans and "làm ngay" in ans.lower(), ans[:300])
ok("sự cố khẩn: có trích dẫn văn bản", bool(re.search(r"\[#\d+\]", ans)) and any(e["type"] == "sources" and e["sources"] for e in ev), ans[:200])
saved = next((e for e in ev if e["type"] == "message_saved"), None)
if saved:
    steps = [s["node_type"] for s in c.get(f"/v1/audit/runs/{saved['run_id']}", headers=A).json().get("steps", [])]
    ok("sự cố khẩn: nhật ký có bước trích tham số và rẽ nhánh", "parameter_extract" in steps and "if_else" in steps, steps)
ev = staff_chat(S_LEGAL, incident["id"], "Quà tặng từ khách hàng trên mức nào thì phải khai báo?")
ans = answer_of(ev)
ok("câu hỏi thường: không cảnh báo khẩn, trả lời ngưỡng 2 triệu có trích dẫn",
   "⚠️" not in ans and "2" in ans and re.search(r"\[#\d+\]", ans), ans[:300])

# --------------------------------------------------------------------------- 6. ba luồng báo cáo mới → Excel có biểu đồ
from openpyxl import load_workbook  # noqa: E402

REPORTS = [
    ("Báo cáo giao dịch TTQT theo ngày (Excel)", OPS, {"so_ngay": 7}, ["Theo ngày", "Đang xử lý"], ["LineChart", "BarChart"]),
    ("Báo cáo huy động & cho vay KHCN tháng (Excel)", RB, {"thang": "09/2026"}, ["Chi nhánh", "Xu hướng cho vay"], ["BarChart", "PieChart", "LineChart"]),
    ("Báo cáo khiếu nại giao dịch tháng (Excel)", OPS, {"thang": "09/2026"}, ["Theo loại", "Đang quá hạn"], ["BarChart"]),
    ("Báo cáo kinh doanh tháng (Excel)", EB, {"thang": "09/2026"}, ["Doanh số chi nhánh", "Nợ theo nhóm", "KPI cán bộ"], ["BarChart", "PieChart", "BarChart", "BarChart"]),
]
jobs = []
for name, H, inputs, _, _ in REPORTS:
    wf = next(w for w in wfs if w["name"] == name)
    r = c.post(f"/v1/workflows/{wf['id']}/jobs", headers=H, json={"query": "bao cao", "inputs": inputs})
    ok(f"xếp hàng chạy: {name}", r.status_code == 202, r.text[:200])
    jobs.append((wf, H, r.json().get("run_id") if r.status_code == 202 else None))

for (name, H, _, sheets, chart_kinds), (wf, _, run_id) in zip(REPORTS, jobs):
    row = {}
    for _ in range(75):
        time.sleep(4)
        row = next((x for x in c.get(f"/v1/workflows/{wf['id']}/runs", headers=H).json() if x["id"] == run_id), {})
        if row.get("status") in ("completed", "failed"):
            break
    ok(f"chạy xong: {name}", row.get("status") == "completed", {k: row.get(k) for k in ("status", "error")})
    arts = {a["content_type"].split(";")[0]: a for a in row.get("artifacts", [])}
    xlsx = arts.get(XLSX_MIME)
    if not ok(f"sinh Excel + Markdown: {name}", xlsx is not None and "text/markdown" in arts, list(arts)):
        continue
    wb = load_workbook(io.BytesIO(c.get(f"/v1/artifacts/{xlsx['id']}/download", headers=H).content))
    ok(f"đúng sheet: {name}", wb.sheetnames == sheets, wb.sheetnames)
    found = [type(ch).__name__ for ws in wb.worksheets for ch in ws._charts]
    ok(f"Excel có biểu đồ thật ({', '.join(chart_kinds)}): {name}", sorted(found) == sorted(chart_kinds), found)
    first = wb[sheets[0]]
    ok(f"sheet đầu có dữ liệu số từ mock: {name}",
       any(isinstance(cell.value, (int, float)) and cell.value > 0 for row_ in first.iter_rows() for cell in row_), None)
    for a in row.get("artifacts", []):
        c.delete(f"/v1/artifacts/{a['id']}", headers=H)

# --------------------------------------------------------------------------- 7. biểu mẫu điền sẵn từ điện SWIFT
form = next(f for f in c.get("/v1/staff/forms", headers=S_OPS).json() if "tra soát điện" in f["name"].lower())
r = c.post(f"/v1/staff/forms/{form['id']}/prefill", headers=S_OPS, json={"key": "TTR2026-1162"})
vals = r.json().get("values", {}) if r.status_code == 200 else {}
ok("biểu mẫu OPS: điền sẵn ngân hàng hưởng và trạng thái từ SWIFT gpi",
   r.status_code == 200 and "Kookmin" in str(vals.get("ngan_hang_huong")) and vals.get("so_tien_usd") == 74300, r.text[:300])
rb_form = next(f for f in c.get("/v1/staff/forms", headers=S_RB).json() if "thẩm định vay" in f["name"].lower())
r = c.post(f"/v1/staff/forms/{rb_form['id']}/prefill", headers=S_RB, json={"key": "HSCN2026-0101"})
vals = r.json().get("values", {}) if r.status_code == 200 else {}
ok("biểu mẫu RB: điền sẵn LTV và nhóm nợ CIC từ hồ sơ KHCN", r.status_code == 200 and vals.get("ltv_phan_tram") == 69.2 and vals.get("cic_nhom_no") == 1, r.text[:300])
legal_forms = [f["name"] for f in c.get("/v1/staff/forms", headers=S_RB).json()]
ok("biểu mẫu Pháp chế chia sẻ toàn ngân hàng: cán bộ KHCN cũng thấy", any("sự cố bảo mật" in n.lower() for n in legal_forms), legal_forms)

# --------------------------------------------------------------------------- kết quả
passed = sum(1 for _, v in results if v)
print(f"\n{passed}/{len(results)} PASS")
sys.exit(0 if passed == len(results) else 1)
