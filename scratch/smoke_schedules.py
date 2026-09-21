"""Lịch chạy báo cáo: cron, ticker tự kích hoạt, chạy ngay, giao báo cáo cho cán bộ theo chức danh.

Cần: API :8000, jobs worker, scheduler (`python -m app.scheduler`), mock core :8095, provider LLM.
Chạy:  apps/api/.venv/bin/python scratch/smoke_schedules.py
       API=https://<domain> ADMIN_PASSWORD=... apps/api/.venv/bin/python scratch/smoke_schedules.py
"""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=180)
results = []
VN = timezone(timedelta(hours=7))


def ok(label, cond, extra=""):
    results.append((label, bool(cond)))
    print(("PASS " if cond else "FAIL ") + label, "" if cond else "→ " + str(extra)[:300])
    return bool(cond)


tok = c.post("/v1/auth/login", json={"email": "admin@querion.io",
                                     "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}
ws = {w["name"]: w["id"] for w in c.get("/v1/audit/filters", headers=A).json()["workspaces"]}
EB = {**A, "X-Workspace-Id": ws["Khối Khách hàng Doanh nghiệp (EB)"]}
OPS = {**A, "X-Workspace-Id": ws["Khối Vận hành & Thanh toán quốc tế"]}
tag = uuid.uuid4().hex[:6]

reports = [w for w in c.get("/v1/workflows", headers=EB).json() if w["type"] == "report"]
# chọn đúng luồng SLA (đơn vị có nhiều luồng báo cáo), để kiểm tra nội dung bản Markdown
wf = next((w for w in reports if "quá hạn SLA" in w["name"]), reports[0] if reports else None)
if not ok("có luồng báo cáo để đặt lịch", wf is not None):
    sys.exit(1)

status = c.get("/v1/schedules/status", headers=EB).json()
ok("bộ lập lịch đang chạy (heartbeat)", status.get("running") is True, status)

# ---- cron helpers
pv = c.get("/v1/schedules/preview", headers=EB, params={"cron": "30 7 * * 1-5"}).json()
ok("xem trước cron: mô tả tiếng Việt + 5 lần kế", pv["cron_label"].startswith("07:30") and len(pv["next_runs"]) == 5, pv)
bad = c.get("/v1/schedules/preview", headers=EB, params={"cron": "khong phai cron"})
ok("cron sai bị từ chối (400)", bad.status_code == 400, bad.text[:120])

created = []
try:
    # ---- create
    r = c.post("/v1/schedules", headers=EB, json={
        "workflow_id": wf["id"], "name": f"Lịch sáng {tag}", "cron": "30 7 * * 1-5",
        "inputs": {"chi_qua_han": True, "chi_nhanh": ""}, "deliver_positions": ["CCO", "RM"], "retention_days": 7})
    ok("tạo lịch: 201 + lần chạy kế được tính", r.status_code == 201 and r.json().get("next_run_at"), r.text[:200])
    sch = r.json()
    created.append(sch["id"])
    ok("mô tả cron hiển thị được", sch["cron_label"] == "07:30 các ngày làm việc (T2–T6)", sch["cron_label"])
    nxt = datetime.fromisoformat(sch["next_run_at"]).astimezone(VN)
    ok("giờ chạy kế đúng 07:30 giờ VN, ngày làm việc", nxt.hour == 7 and nxt.minute == 30 and nxt.weekday() < 5, nxt.isoformat())

    r = c.post("/v1/schedules", headers=EB, json={"workflow_id": wf["id"], "name": "x", "cron": "99 99 * * *"})
    ok("cron sai khi tạo bị chặn (400)", r.status_code == 400, r.text[:120])
    r = c.post("/v1/schedules", headers=OPS, json={"workflow_id": wf["id"], "name": "x", "cron": "0 8 * * *"})
    ok("không đặt lịch cho luồng của đơn vị khác (404)", r.status_code == 404, r.text[:120])
    r = c.post("/v1/schedules", headers=EB, json={"workflow_id": wf["id"], "name": "x", "cron": "0 8 * * *",
                                                  "deliver_positions": ["SEP"]})
    ok("chức danh không hợp lệ bị chặn (400)", r.status_code == 400, r.text[:120])

    # ---- the ticker fires a due schedule on its own
    due = c.post("/v1/schedules", headers=EB, json={
        "workflow_id": wf["id"], "name": f"Lịch đến hạn {tag}", "cron": "*/1 * * * *",
        "inputs": {"chi_qua_han": True, "chi_nhanh": ""}, "deliver_positions": ["RM"], "retention_days": 2}).json()
    created.append(due["id"])
    fired = None
    for _ in range(50):  # ticker mỗi 30s + job chạy nền
        time.sleep(5)
        row = next((s for s in c.get("/v1/schedules", headers=EB).json() if s["id"] == due["id"]), {})
        if row.get("last_run_id"):
            fired = row
            break
    ok("ticker tự kích hoạt lịch đến hạn", fired is not None, "không thấy last_run_id sau ~4 phút")
    if fired:
        ok("lịch dời sang lần chạy kế sau khi kích hoạt", fired["next_run_at"] > fired["last_enqueued_at"], fired)
        arts = []
        for _ in range(40):
            arts = c.get("/v1/artifacts", headers=EB, params={"schedule_id": due["id"]}).json()
            if arts:
                break
            time.sleep(5)
        ok("lần chạy theo lịch sinh ra tệp báo cáo", len(arts) > 0, arts)
        run = c.get(f"/v1/audit/runs/{fired['last_run_id']}", headers=A).json()
        ok("nhật ký ghi channel=scheduled", run.get("channel") == "scheduled", run.get("channel"))

    # ---- run now
    r = c.post(f"/v1/schedules/{sch['id']}/run-now", headers=EB)
    ok("chạy ngay: 202 + run_id", r.status_code == 202 and r.json().get("run_id"), r.text[:160])
    manual_run = r.json()["run_id"]
    for _ in range(40):
        detail = c.get(f"/v1/audit/runs/{manual_run}", headers=A).json()
        if detail.get("status") in ("completed", "failed"):
            break
        time.sleep(5)
    ok("chạy ngay hoàn thành", detail.get("status") == "completed", detail.get("status"))

    # ---- staff inbox honours deliver_positions (RM thấy, GDV/khác đơn vị không thấy)
    st_rm = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"}).json()["access_token"]
    rm_reports = c.get("/v1/staff/reports", headers={"Authorization": f"Bearer {st_rm}"}).json()
    ok("cán bộ RM nhận được báo cáo theo lịch", any(x.get("schedule_name", "").endswith(tag) for x in rm_reports),
       [x.get("schedule_name") for x in rm_reports][:5])
    mine = [x for x in rm_reports if (x.get("schedule_name") or "").endswith(tag)]
    ok("nhận cả bản Markdown và bản Word", len({x["content_type"].split(";")[0] for x in mine}) == 2,
       [x["content_type"] for x in mine])
    target = next((x for x in mine if x["content_type"].startswith("text/markdown")), None)
    if target:
        ok("bản Markdown xem nhanh được ngay trong cổng cán bộ",
           bool(target.get("preview")) and "Mã hồ sơ" in (target.get("preview") or ""), target.get("title"))
        dl = c.get(f"/v1/staff/reports/{target['id']}/download", headers={"Authorization": f"Bearer {st_rm}"})
        ok("cán bộ tải được báo cáo của mình", dl.status_code == 200 and len(dl.content) > 100, dl.status_code)

    st_ca = c.post("/v1/staff/login", json={"email": "ca.binh@msb-demo.vn", "password": "demo123"}).json()["access_token"]
    ca_reports = c.get("/v1/staff/reports", headers={"Authorization": f"Bearer {st_ca}"}).json()
    ok("cán bộ CA (không nằm trong chức danh nhận) không thấy báo cáo đó",
       not any((x.get("schedule_name") or "").endswith(tag) for x in ca_reports), [x.get("schedule_name") for x in ca_reports][:5])
    if target:
        deny = c.get(f"/v1/staff/reports/{target['id']}/download", headers={"Authorization": f"Bearer {st_ca}"})
        ok("cán bộ ngoài danh sách không tải được (404)", deny.status_code == 404, deny.status_code)

    st_ops = c.post("/v1/staff/login", json={"email": "gdv.cuong@msb-demo.vn", "password": "demo123"}).json()["access_token"]
    ops_reports = c.get("/v1/staff/reports", headers={"Authorization": f"Bearer {st_ops}"}).json()
    ok("cán bộ đơn vị khác không thấy báo cáo của EB",
       not any((x.get("schedule_name") or "").endswith(tag) for x in ops_reports), len(ops_reports))

    # ---- enable / disable
    off = c.patch(f"/v1/schedules/{sch['id']}", headers=EB, json={"enabled": False}).json()
    ok("tắt lịch: enabled=false, không còn lần chạy kế", off["enabled"] is False and off["next_run_at"] is None, off)
    on = c.patch(f"/v1/schedules/{sch['id']}", headers=EB, json={"enabled": True}).json()
    ok("bật lại: tính lại lần chạy kế trong tương lai",
       on["enabled"] and datetime.fromisoformat(on["next_run_at"]) > datetime.now(timezone.utc), on["next_run_at"])

    # ---- unit scoping
    ok("đơn vị khác không thấy lịch", sch["id"] not in [s["id"] for s in c.get("/v1/schedules", headers=OPS).json()])
    ok("đơn vị khác không sửa được lịch (404)",
       c.patch(f"/v1/schedules/{sch['id']}", headers=OPS, json={"enabled": False}).status_code == 404)
finally:
    for sid in created:
        c.delete(f"/v1/schedules/{sid}", headers=EB)
    ok("xoá lịch thử", all(sid not in [s["id"] for s in c.get("/v1/schedules", headers=EB).json()] for sid in created))
    left = c.get("/v1/artifacts", headers=EB, params={"days": 1}).json()
    for a in left:
        if a.get("schedule_id") in created:
            c.delete(f"/v1/artifacts/{a['id']}", headers=EB)

passed = sum(1 for _, v in results if v)
print(f"\n===== SCHEDULES: {passed}/{len(results)} passed =====")
sys.exit(0 if passed == len(results) else 1)
