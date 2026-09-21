"""Day-1 smoke test: audience/visibility validation, staff app listing, staff chat envelope."""
import json, sys, uuid
import os
import httpx

API = os.environ.get("API", "http://localhost:8000")
c = httpx.Client(base_url=API, timeout=30)

def ok(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label, extra)
    if not cond:
        sys.exit(1)

tok = c.post("/v1/auth/login", json={"email": "admin@querion.io", "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
A = {"Authorization": f"Bearer {tok}"}

# admin user to own the workspace
suffix = uuid.uuid4().hex[:6]
u = c.post("/v1/users", headers=A, json={"email": f"admin.khcn.{suffix}@msb-demo.vn", "password": "demo123", "name": "Admin KHCN"})
ok("create admin user", u.status_code == 201, u.text[:120])
uid = u.json()["id"]

ws = c.post("/v1/workspaces", headers=A, json={"name": f"Khối KHCN {suffix}", "owner_user_id": uid})
ok("create workspace", ws.status_code == 201, ws.text[:120])
wsid = ws.json()["id"]
W = {**A, "X-Workspace-Id": wsid}

ds = c.post("/v1/datasets", headers=W, json={"name": "Kho nội bộ", "visibility": "internal"})
ok("create internal dataset", ds.status_code == 201 and ds.json()["visibility"] == "internal", ds.text[:120])
dsid = ds.json()["id"]

bad = c.post("/v1/apps", headers=W, json={"name": "Trợ lý KH", "dataset_ids": [dsid], "audience": "customer"})
ok("customer app on internal dataset rejected (400)", bad.status_code == 400, bad.text[:160])

badaud = c.post("/v1/apps", headers=W, json={"name": "x", "audience": "partner"})
ok("unknown audience rejected (400)", badaud.status_code == 400, badaud.text[:120])

pt = c.patch(f"/v1/datasets/{dsid}", headers=W, json={"visibility": "public"})
ok("patch dataset -> public", pt.status_code == 200 and pt.json()["visibility"] == "public", pt.text[:120])

capp = c.post("/v1/apps", headers=W, json={"name": "Trợ lý Khách hàng", "dataset_ids": [dsid], "audience": "customer", "description": "public"})
ok("create customer app", capp.status_code == 201 and capp.json()["audience"] == "customer" and capp.json()["api_key"].startswith("app-"), capp.text[:160])
cappid = capp.json()["id"]
c.patch(f"/v1/apps/{cappid}", headers=W, json={"is_published": True})

sapp = c.post("/v1/apps", headers=W, json={"name": "Trợ lý Tín dụng KHCN", "dataset_ids": [dsid]})
ok("create staff app (default audience=staff)", sapp.status_code == 201 and sapp.json()["audience"] == "staff", sapp.text[:160])
sappid = sapp.json()["id"]
c.patch(f"/v1/apps/{sappid}", headers=W, json={"is_published": True})

# flipping a published staff app to customer while bound to public dataset is fine; to internal must fail
c.patch(f"/v1/datasets/{dsid}", headers=W, json={"visibility": "internal"})
flip = c.patch(f"/v1/apps/{sappid}", headers=W, json={"audience": "customer"})
ok("flip to customer with internal dataset rejected (400)", flip.status_code == 400, flip.text[:120])
c.patch(f"/v1/datasets/{dsid}", headers=W, json={"visibility": "public"})

# staff portal
st = c.post("/v1/staff/login", json={"email": "rm.an@msb-demo.vn", "password": "demo123"})
ok("staff login", st.status_code == 200, st.text[:120])
S = {"Authorization": f"Bearer {st.json()['access_token']}"}
apps = c.get("/v1/staff/apps", headers=S).json()
names = [a["name"] for g in apps for a in g["apps"]]
# rm.an belongs to the EB unit; the new app lives in a fresh unit → hidden until its owner opens it bank-wide
ok("unit scoping: staff of another unit sees neither the unit-only staff app nor the customer app",
   "Trợ lý Tín dụng KHCN" not in names and "Trợ lý Khách hàng" not in names, str(names)[:200])
r = c.post(f"/v1/staff/apps/{sappid}/chat", headers=S, json={"message": "hi"})
ok("staff of another unit cannot chat with a unit-only app (404)", r.status_code == 404, r.text[:120])
sh = c.patch(f"/v1/apps/{sappid}", headers=W, json={"share_scope": "bank"})
ok("owner opens the staff app bank-wide", sh.status_code == 200 and sh.json()["share_scope"] == "bank", sh.text[:160])
names = [a["name"] for g in c.get("/v1/staff/apps", headers=S).json() for a in g["apps"]]
ok("after sharing bank-wide, staff of other units see it (customer app still hidden)", "Trợ lý Tín dụng KHCN" in names and "Trợ lý Khách hàng" not in names, str(names)[:200])

# staff chat on customer app -> 404
r = c.post(f"/v1/staff/apps/{cappid}/chat", headers=S, json={"message": "hi"})
ok("staff cannot chat with customer app (404)", r.status_code == 404, r.text[:120])

# staff chat on staff app: SSE envelope (no LLM provider configured -> error event, but conversation_id first)
events = []
with c.stream("POST", f"/v1/staff/apps/{sappid}/chat", headers=S, json={"message": "Điều kiện giải ngân?"}) as resp:
    ok("staff chat 200 + event-stream", resp.status_code == 200 and "text/event-stream" in resp.headers.get("content-type", ""), str(resp.headers.get("content-type")))
    for line in resp.iter_lines():
        if line.startswith("data: "):
            events.append(line[6:])
types = [json.loads(e)["type"] for e in events if e != "[DONE]"]
ok("SSE: conversation_id first, then sources/error, then [DONE]", types[0] == "conversation_id" and "[DONE]" in events and ("error" in types or "token" in types), str(types))

convs = c.get(f"/v1/staff/apps/{sappid}/conversations", headers=S).json()
ok("conversation persisted for employee", len(convs) >= 1 and convs[0]["message_count"] >= 1, str(convs)[:160])

# cleanup — must actually succeed, otherwise leftovers pollute later runs
d1 = c.delete(f"/v1/workspaces/{wsid}", headers=A)
ok("cleanup: workspace deleted (owner membership cascades)", d1.status_code == 200, d1.text[:160])
d2 = c.delete(f"/v1/users/{uid}", headers=A)
ok("cleanup: admin user deleted", d2.status_code in (200, 204), d2.text[:160])
print("ALL PASS")
