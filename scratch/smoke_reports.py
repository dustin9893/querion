"""Luồng báo cáo: chạy nền, gọi công cụ thật, xuất file Markdown + DOCX, tải về theo đơn vị.

Cần: API :8000, jobs worker (`python -m app.jobs.worker`), mock core :8095, provider LLM + embedding.
Chạy:  apps/api/.venv/bin/python scratch/smoke_reports.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_reports.py   # trên server
"""
import io
import os
import sys
import time
import uuid
import zipfile

import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=240)
results = []


def ok(label, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, "" if cond else "→ " + str(extra)[:300])
    return bool(cond)


def wait_run(run_id, headers, timeout=240):
    end = time.time() + timeout
    last = {}
    while time.time() < end:
        rows = c.get(f"/v1/workflows/{WF['id']}/runs", headers=headers).json()
        last = next((r for r in rows if r["id"] == run_id), {})
        if last.get("status") in ("completed", "failed", "blocked"):
            return last
        time.sleep(3)
    return last


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io",
                                     "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
ws = {w["name"]: w["id"] for w in c.get("/v1/audit/filters", headers=A).json()["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
OPS = {**A, "X-Workspace-Id": ws["Khối Vận hành & Thanh toán quốc tế"]}

WF = next((w for w in c.get("/v1/workflows", headers=EB).json()
           if w["name"] == "Báo cáo hồ sơ tín dụng quá hạn SLA"), None)
if not ok("có luồng báo cáo mẫu sau khi seed", WF is not None):
    sys.exit(1)
ok("luồng báo cáo có type=report", WF["type"] == "report", WF["type"])
nodes = {n["id"]: n for n in WF["graph_json"]["nodes"]}
ok("node input khai báo tham số (fields)", len(nodes["input"]["data"].get("fields") or []) == 2, nodes["input"]["data"])
ok("có node gọi công cụ và node xuất file", nodes["lay_ho_so"]["type"] == "tool_call"
   and nodes["xuat_md"]["type"] == "render_document", list(nodes))

# ---- 1. chạy nền
r = c.post(f"/v1/workflows/{WF['id']}/jobs", headers=EB, json={"query": "bao cao", "inputs": {"chi_qua_han": True, "chi_nhanh": ""}})
ok("xếp hàng chạy nền: 202 + run_id", r.status_code == 202 and r.json().get("run_id"), r.text[:200])
run_id = r.json()["run_id"]
row = wait_run(run_id, EB)
ok("chạy xong trạng thái completed", row.get("status") == "completed", row)
arts = {a["content_type"].split(";")[0]: a for a in row.get("artifacts", [])}
ok("sinh 2 tệp: Markdown + DOCX", set(arts) == {"text/markdown",
   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}, list(arts))

# ---- 2. nội dung báo cáo
md = arts.get("text/markdown")
detail = c.get(f"/v1/artifacts/{md['id']}", headers=EB).json()
preview = detail.get("preview") or ""
ok("Markdown có bảng hồ sơ lấy từ hệ thống lõi", "HS2026-0412" in preview and "| Mã hồ sơ |" in preview, preview[:200])
ok("Markdown có số tiền định dạng VN", "12.000.000.000 đ" in preview, preview[:400])
ok("Markdown có phần nhận định do LLM viết", "## Nhận định và việc cần làm" in preview
   and len(preview.split("## Nhận định và việc cần làm")[1].strip()) > 80, preview[-400:])
ok("chỉ liệt kê hồ sơ quá hạn (không có HS2026-0620 còn hạn)", "HS2026-0620" not in preview, preview[:600])

dl = c.get(f"/v1/artifacts/{md['id']}/download", headers=EB)
ok("tải Markdown: đúng content-type và tên tệp", dl.status_code == 200
   and dl.headers["content-type"].startswith("text/markdown")
   and "attachment" in dl.headers.get("content-disposition", ""), dl.headers.get("content-disposition"))

docx = arts.get("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
dl_docx = c.get(f"/v1/artifacts/{docx['id']}/download", headers=EB)
body = dl_docx.content
ok("tải DOCX: là tệp docx hợp lệ", dl_docx.status_code == 200 and body[:2] == b"PK" and len(body) > 5000, len(body))
try:
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
except Exception as exc:  # noqa: BLE001
    xml = f"lỗi đọc docx: {exc}"
ok("DOCX đã điền dữ liệu (không còn placeholder)", "HS2026-0412" in xml and "{{" not in xml and "{%" not in xml,
   [s for s in ("HS2026-0412" in xml, "{{" in xml, "{%" in xml)])
ok("DOCX có nhận định của LLM", "Nhận định" in xml and len(xml) > 4000)

# ---- 3. phạm vi đơn vị + nhật ký
ok("đơn vị khác không tải được tệp (404)", c.get(f"/v1/artifacts/{md['id']}/download", headers=OPS).status_code == 404)
ok("đơn vị khác không thấy tệp trong danh sách",
   md["id"] not in [a["id"] for a in c.get("/v1/artifacts", headers=OPS).json()])
listed = c.get("/v1/artifacts", headers=EB, params={"workflow_id": WF["id"]}).json()
ok("danh sách tệp lọc theo luồng", md["id"] in [a["id"] for a in listed], len(listed))

audit = c.get(f"/v1/audit/runs/{run_id}", headers=A).json()
ok("nhật ký truy vấn ghi lượt chạy báo cáo (channel=report)", audit.get("channel") == "report", audit.get("channel"))
steps = {s["node_type"] for s in audit.get("steps", [])}
ok("nhật ký có bước gọi công cụ và bước xuất file", {"tool_call", "render_document"} <= steps, steps)
ok("báo cáo có ghi token (nhúng câu hỏi + LLM)", audit.get("total_tokens", 0) > 0, audit.get("total_tokens"))

# ---- 4. kiểm tra tham số đầu vào
r = c.post(f"/v1/workflows/{WF['id']}/jobs", headers=EB, json={"query": "x", "inputs": {"chi_nhanh": "CN Hà Nội", "chi_qua_han": True}})
row2 = wait_run(r.json()["run_id"], EB)
md2 = next((a for a in row2.get("artifacts", []) if a["content_type"].startswith("text/markdown")), None)
prev2 = c.get(f"/v1/artifacts/{md2['id']}", headers=EB).json().get("preview", "") if md2 else ""
ok("lọc theo chi nhánh: chỉ còn hồ sơ CN Hà Nội", bool(md2) and "HS2026-0412" in prev2 and "HS2026-0845" not in prev2, prev2[:300])

# ---- 5. tải mẫu DOCX lên + kiểm mẫu hỏng
bad = c.post(f"/v1/workflows/{WF['id']}/template", headers=EB,
             files={"file": ("mau.txt", b"khong phai docx", "text/plain")})
ok("từ chối mẫu không phải .docx (400)", bad.status_code == 400, bad.text[:120])
good_docx = c.get(f"/v1/artifacts/{docx['id']}/download", headers=EB).content  # tệp đã render vẫn là .docx hợp lệ
up = c.post(f"/v1/workflows/{WF['id']}/template", headers=EB,
            files={"file": ("mau-moi.docx", good_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
ok("tải mẫu .docx lên trả về template_key", up.status_code == 200 and up.json().get("template_key", "").startswith("templates/"), up.text[:200])

# ---- 6. dọn dẹp tệp thử
for art in list(arts.values()) + ([md2] if md2 else []):
    c.delete(f"/v1/artifacts/{art['id']}", headers=EB)
ok("xoá tệp thử", c.get(f"/v1/artifacts/{md['id']}", headers=EB).status_code == 404)

passed = sum(1 for _, v in results if v)
print(f"\n===== REPORTS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
