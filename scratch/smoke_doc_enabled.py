"""Bật / tắt văn bản trong kho tri thức: văn bản đã tắt không được AI truy vấn ở mọi đường trả lời.

Cần: API :8000, worker, provider embedding + LLM đang bật. Tự tạo và tự xoá kho + trợ lý tạm.
Chạy:  apps/api/.venv/bin/python scratch/smoke_doc_enabled.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_doc_enabled.py   # trên server
"""
import json
import os
import sys
import time
import uuid

import httpx

API = os.environ.get("API", "http://localhost:8000")
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


def wait_ready(doc_id, H, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(f"/v1/documents/{doc_id}", headers=H).json()
        if d["status"] in ("ready", "failed"):
            return d
        time.sleep(2)
    return d


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
ws = {w["name"]: w["id"] for w in c.get("/v1/audit/filters", headers=A).json()["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
tag = uuid.uuid4().hex[:6].upper()

# Synthetic content only. A = the document we toggle, B = a control that must stay retrievable.
DOC_A = (f"Điều 1. Phí thẩm định hồ sơ thử nghiệm {tag}\n"
         f"Phí thẩm định hồ sơ thử nghiệm mã {tag} là 12.345 đồng mỗi hồ sơ, thu một lần khi nộp hồ sơ.\n")
DOC_B = ("Điều 1. Giờ làm việc của quầy thử nghiệm\n"
         "Quầy giao dịch thử nghiệm mở cửa từ 8 giờ đến 17 giờ các ngày làm việc trong tuần.\n")
QUESTION = f"Phí thẩm định hồ sơ thử nghiệm mã {tag} là bao nhiêu?"

ds = c.post("/v1/datasets", headers=EB, json={"name": f"Kiểm thử bật tắt {tag}", "visibility": "internal"}).json()
app = None
try:
    docs = {}
    for name, body in (("a", DOC_A), ("b", DOC_B)):
        r = c.post(f"/v1/datasets/{ds['id']}/documents/upload", headers=EB,
                   files={"file": (f"thu_nghiem_{name}_{tag}.txt", body.encode(), "text/plain")},
                   data={"doc_type": "bieu_phi"})
        docs[name] = r.json()
    ok("văn bản mới mặc định được bật", all(d.get("enabled") is True for d in docs.values()), docs)
    ready = {k: wait_ready(d["id"], EB) for k, d in docs.items()}
    if not ok("lập chỉ mục xong", all(d["status"] == "ready" for d in ready.values()), ready):
        sys.exit(1)
    a_id, b_id = docs["a"]["id"], docs["b"]["id"]

    def retrieved():
        r = c.post("/v1/retrieval", headers=EB, json={"query": QUESTION, "dataset_ids": [ds["id"]], "top_k": 10})
        return {x["document_id"] for x in r.json()["results"]}

    app = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý kiểm thử bật tắt {tag}", "dataset_ids": [ds["id"]]}).json()

    def test_chat():
        with c.stream("POST", f"/v1/apps/{app['id']}/test-chat", headers=EB, json={"message": QUESTION}) as r:
            ev = sse(r)
        src = {s.get("document_id") for e in ev if e["type"] == "sources" for s in e["sources"]}
        answer = "".join(e["content"] for e in ev if e["type"] == "token")
        return src, answer

    # ---- enabled
    ok("đang bật: /v1/retrieval trả về văn bản A", a_id in retrieved())
    src, answer = test_chat()
    ok("đang bật: trợ lý trích dẫn văn bản A", a_id in src, src)
    ok("đang bật: câu trả lời có số liệu của A (12.345)", "12.345" in answer or "12345" in answer, answer[:200])

    # ---- disable
    r = c.patch(f"/v1/documents/{a_id}", headers=EB, json={"enabled": False})
    body = r.json()
    ok("tắt văn bản: 200, enabled=false, có disabled_at", r.status_code == 200 and body["enabled"] is False and body["disabled_at"], body)
    detail = c.get(f"/v1/datasets/{ds['id']}", headers=EB).json()
    ok("chi tiết kho hiển thị trạng thái đã tắt", next(d for d in detail["documents"] if d["id"] == a_id)["enabled"] is False)
    got = retrieved()
    ok("đã tắt: /v1/retrieval không còn A", a_id not in got, got)
    ok("đã tắt: văn bản B vẫn truy vấn được", b_id in got, got)
    src, answer = test_chat()
    ok("đã tắt: trợ lý không trích dẫn A", a_id not in src, src)
    ok("đã tắt: câu trả lời không còn số liệu của A", "12.345" not in answer and "12345" not in answer, answer[:200])

    # ---- metadata edits and re-indexing must not turn it back on
    r = c.patch(f"/v1/documents/{a_id}", headers=EB, json={"version": "v2"})
    ok("sửa metadata không bật lại văn bản", r.json()["enabled"] is False, r.json())
    c.post(f"/v1/documents/{a_id}/index", headers=EB)
    d = wait_ready(a_id, EB)
    ok("lập chỉ mục lại vẫn giữ trạng thái tắt", d["status"] == "ready" and d["enabled"] is False, d)
    ok("sau khi lập chỉ mục lại: vẫn không truy vấn A", a_id not in retrieved())

    # ---- enable again
    r = c.patch(f"/v1/documents/{a_id}", headers=EB, json={"enabled": True})
    ok("bật lại: enabled=true, xoá disabled_at", r.json()["enabled"] is True and r.json()["disabled_at"] is None, r.json())
    ok("bật lại: truy vấn được A ngay", a_id in retrieved())
    src, _ = test_chat()
    ok("bật lại: trợ lý trích dẫn A", a_id in src, src)

    # ---- scoping: another unit cannot toggle it
    ops = {**A, "X-Workspace-Id": ws["Khối Vận hành & Thanh toán quốc tế"]}
    r = c.patch(f"/v1/documents/{a_id}", headers=ops, json={"enabled": False})
    ok("đơn vị khác không tắt được văn bản (404)", r.status_code == 404, r.status_code)
finally:
    if app and app.get("id"):
        c.delete(f"/v1/apps/{app['id']}", headers=EB)
    c.delete(f"/v1/datasets/{ds['id']}", headers=EB)
    ok("dọn dẹp kho + trợ lý tạm", c.get(f"/v1/datasets/{ds['id']}", headers=EB).status_code == 404)

passed = sum(1 for _, v in results if v)
print(f"\n===== DOC ENABLED: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
