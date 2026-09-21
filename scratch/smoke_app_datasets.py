"""Một trợ lý gắn nhiều kho tri thức: truy vấn trên tất cả kho, ràng buộc đơn vị và kho công khai.

Cần: API :8000, worker, provider embedding + LLM đang bật. Tự tạo và tự xoá kho + trợ lý tạm.
Chạy:  apps/api/.venv/bin/python scratch/smoke_app_datasets.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_app_datasets.py   # trên server
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


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
ws = {w["name"]: w["id"] for w in c.get("/v1/audit/filters", headers=A).json()["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
OPS = {**A, "X-Workspace-Id": ws["Khối Vận hành & Thanh toán quốc tế"]}
tag = uuid.uuid4().hex[:6].upper()

# Synthetic facts, one per knowledge base, so a citation proves which base was searched.
FACT_INTERNAL = f"Điều 1. Phí thẩm định hồ sơ mã {tag}\nPhí thẩm định hồ sơ mã {tag} là 45.678 đồng mỗi hồ sơ.\n"
FACT_PUBLIC = f"Điều 1. Giờ mở cửa quầy mã {tag}\nQuầy giao dịch mã {tag} mở cửa từ 7 giờ 30 đến 16 giờ 45.\n"
QUESTION = f"Với mã {tag}: phí thẩm định hồ sơ là bao nhiêu và quầy giao dịch mở cửa mấy giờ?"

created = {"datasets": [], "apps": []}


def make_dataset(name, visibility, body):
    ds = c.post("/v1/datasets", headers=EB, json={"name": f"{name} {tag}", "visibility": visibility}).json()
    created["datasets"].append(ds["id"])
    doc = c.post(f"/v1/datasets/{ds['id']}/documents/upload", headers=EB,
                 files={"file": (f"{visibility}_{tag}.txt", body.encode(), "text/plain")}).json()
    return ds, doc


def wait_ready(doc_id):
    for _ in range(90):
        d = c.get(f"/v1/documents/{doc_id}", headers=EB).json()
        if d["status"] in ("ready", "failed"):
            return d
        time.sleep(2)
    return d


def ask(app_id):
    with c.stream("POST", f"/v1/apps/{app_id}/test-chat", headers=EB, json={"message": QUESTION}) as r:
        ev = sse(r)
    docs = {s.get("document_id") for e in ev if e["type"] == "sources" for s in e["sources"]}
    return docs, "".join(e["content"] for e in ev if e["type"] == "token")


try:
    ds_int, doc_int = make_dataset("Kho nội bộ kiểm thử", "internal", FACT_INTERNAL)
    ds_pub, doc_pub = make_dataset("Kho công khai kiểm thử", "public", FACT_PUBLIC)
    if not ok("lập chỉ mục 2 kho tạm", all(wait_ready(d["id"])["status"] == "ready" for d in (doc_int, doc_pub))):
        sys.exit(1)

    # ---- staff assistant bound to both
    r = c.post("/v1/apps", headers=EB, json={"name": f"Trợ lý nhiều kho {tag}", "dataset_ids": [ds_int["id"], ds_pub["id"]]})
    app = r.json()
    created["apps"].append(app.get("id"))
    ok("tạo trợ lý gắn 2 kho, giữ đúng thứ tự", r.status_code == 201 and app["dataset_ids"] == [ds_int["id"], ds_pub["id"]], r.text[:200])
    listed = next((a for a in c.get("/v1/apps", headers=EB).json() if a["id"] == app["id"]), {})
    ok("danh sách trợ lý trả về dataset_ids", listed.get("dataset_ids") == [ds_int["id"], ds_pub["id"]], listed.get("dataset_ids"))

    docs, answer = ask(app["id"])
    ok("một câu hỏi trích dẫn được cả 2 kho", {doc_int["id"], doc_pub["id"]} <= docs, docs)
    ok("câu trả lời dùng dữ kiện của cả 2 kho", "45.678" in answer and ("7 giờ 30" in answer or "7:30" in answer or "7h30" in answer), answer[:250])

    # ---- narrow to one
    r = c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"dataset_ids": [ds_pub["id"]]})
    ok("bỏ bớt kho còn 1", r.status_code == 200 and r.json()["dataset_ids"] == [ds_pub["id"]], r.text[:200])
    docs, _ = ask(app["id"])
    ok("sau khi bỏ: không còn trích dẫn kho đã gỡ", doc_int["id"] not in docs and doc_pub["id"] in docs, docs)
    r = c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"name": f"Trợ lý nhiều kho {tag} (đổi tên)"})
    ok("sửa trường khác không làm mất kho đã gắn", r.json()["dataset_ids"] == [ds_pub["id"]], r.text[:200])
    r = c.post(f"/v1/apps/{app['id']}/regenerate-key", headers=EB)
    ok("đổi API key vẫn trả về đủ kho", r.json()["dataset_ids"] == [ds_pub["id"]], r.text[:200])

    # ---- validation
    ops_ds = c.get("/v1/datasets", headers=OPS).json()[0]["id"]
    r = c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"dataset_ids": [ds_pub["id"], ops_ds]})
    ok("không gắn được kho của đơn vị khác (400)", r.status_code == 400, r.text[:160])
    ok("gắn lỗi thì giữ nguyên kho cũ", c.get(f"/v1/apps/{app['id']}", headers=EB).json()["dataset_ids"] == [ds_pub["id"]])
    r = c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"dataset_ids": ["khong-phai-uuid"]})
    ok("dataset_ids sai định dạng (400)", r.status_code == 400, r.text[:160])

    r = c.post("/v1/apps", headers=EB, json={"name": f"KH sai kho {tag}", "audience": "customer", "dataset_ids": [ds_pub["id"], ds_int["id"]]})
    ok("trợ lý khách hàng không gắn được kho nội bộ, báo tên kho (400)", r.status_code == 400 and ds_int["name"] in r.text, r.text[:200])
    r = c.post("/v1/apps", headers=EB, json={"name": f"KH đúng kho {tag}", "audience": "customer", "dataset_ids": [ds_pub["id"]]})
    created["apps"].append(r.json().get("id"))
    ok("trợ lý khách hàng gắn kho công khai", r.status_code == 201, r.text[:160])
    c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"dataset_ids": [ds_int["id"], ds_pub["id"]]})
    r = c.patch(f"/v1/apps/{app['id']}", headers=EB, json={"audience": "customer"})
    ok("đổi sang khách hàng khi đang gắn kho nội bộ bị chặn (400)", r.status_code == 400, r.text[:160])

    # ---- deleting a knowledge base unbinds it
    c.delete(f"/v1/datasets/{ds_int['id']}", headers=EB)
    created["datasets"].remove(ds_int["id"])
    ok("xoá kho thì tự gỡ khỏi trợ lý", c.get(f"/v1/apps/{app['id']}", headers=EB).json()["dataset_ids"] == [ds_pub["id"]])
finally:
    for app_id in filter(None, created["apps"]):
        c.delete(f"/v1/apps/{app_id}", headers=EB)
    for ds_id in created["datasets"]:
        c.delete(f"/v1/datasets/{ds_id}", headers=EB)
    ok("dọn dẹp kho + trợ lý tạm", all(c.get(f"/v1/apps/{a}", headers=EB).status_code == 404 for a in filter(None, created["apps"])))

passed = sum(1 for _, v in results if v)
print(f"\n===== APP DATASETS: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
