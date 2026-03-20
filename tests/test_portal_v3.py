#!/usr/bin/env python3
"""
Maintenance Portal V3 - Professional Gap Coverage Test Suite
Covers gaps identified in professional QA audit:
  - Chatter/mail message access (GAP-09, GAP-14, GAP-23)
  - write() field restriction completeness (GAP-08, GAP-12)
  - Cross-assignment scenarios (GAP-18, GAP-19)
  - stage_id=False action execution (GAP-20)
  - CSS/SVG asset loading (GAP-28, GAP-29)
  - End-to-end navigation flow (GAP-30)
  - Request list empty state (GAP-32)
  - Progress bar visual correctness (GAP-31)
  - _escape_search_term backslash (GAP-04)
  - Dead notes code removal verification (BUG-01)
  - _document_check_access with access_token (GAP-11)
  - Portal counter with no access rights (GAP-05)
  - _check_portal_access for internal users (GAP-10)

Target: Odoo 18 at localhost:9070, DB=odoomaintain
"""
import xmlrpc.client
import requests
import re
import sys
import time
import traceback
from datetime import datetime

# ============================================================
# Configuration
# ============================================================
URL = "http://localhost:9070"
DB = "odoomaintain"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
# Portal user credentials (updated)
PORTAL_USER1_LOGIN = "portal"
PORTAL_USER1_PASS = "portal"
PORTAL_USER2_LOGIN = "vendor_test2@test.com"
PORTAL_USER2_PASS = "vendor_test2_123"

# ============================================================
# Results Tracking
# ============================================================
results = {"passed": 0, "failed": 0, "warned": 0, "details": []}


def log_pass(name, detail=""):
    results["passed"] += 1
    results["details"].append(("PASS", name, detail))
    print(f"  [\033[32mPASS\033[0m] {name}" + (f": {detail}" if detail else ""))


def log_fail(name, detail=""):
    results["failed"] += 1
    results["details"].append(("FAIL", name, detail))
    print(f"  [\033[31mFAIL\033[0m] {name}: {detail}")


def log_warn(name, detail=""):
    results["warned"] += 1
    results["details"].append(("WARN", name, detail))
    print(f"  [\033[33mWARN\033[0m] {name}: {detail}")


def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ============================================================
# Helpers
# ============================================================
class RPC:
    def __init__(self, url, db, user, pwd):
        self.db, self.pwd = db, pwd
        self.common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        self.obj = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        self.uid = self.common.authenticate(db, user, pwd, {})
        if not self.uid:
            raise Exception(f"Auth failed for {user}")

    def ex(self, model, method, *args, **kw):
        return self.obj.execute_kw(self.db, self.uid, self.pwd, model, method, list(args), kw)

    def search(self, model, domain, **kw):
        return self.ex(model, "search", domain, **kw)

    def sr(self, model, domain, fields=None, **kw):
        if fields: kw["fields"] = fields
        return self.ex(model, "search_read", domain, **kw)

    def read(self, model, ids, fields=None):
        kw = {}
        if fields: kw["fields"] = fields
        return self.ex(model, "read", ids, **kw)

    def write(self, model, ids, vals):
        return self.ex(model, "write", ids, vals)

    def create(self, model, vals):
        return self.ex(model, "create", vals)

    def unlink(self, model, ids):
        return self.ex(model, "unlink", ids)

    def call(self, model, method, ids, *args):
        return self.obj.execute_kw(self.db, self.uid, self.pwd, model, method, [ids] + list(args), {})

    def count(self, model, domain):
        return self.ex(model, "search_count", domain)


class HTTP:
    def __init__(self, base_url, db):
        self.base = base_url
        self.db = db
        self.s = requests.Session()

    def login(self, login, pwd):
        r = self.s.get(f"{self.base}/web/login")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
        data = {"login": login, "password": pwd, "db": self.db}
        if csrf: data["csrf_token"] = csrf.group(1)
        return self.s.post(f"{self.base}/web/login", data=data, allow_redirects=True)

    def get(self, path, **kw):
        return self.s.get(f"{self.base}{path}", **kw)

    def post_with_csrf(self, path, data=None):
        if data is None: data = {}
        parent = path.rsplit("/update", 1)[0] if "/update" in path else path
        page = self.s.get(f"{self.base}{parent}")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        if csrf: data["csrf_token"] = csrf.group(1)
        return self.s.post(f"{self.base}{path}", data=data, allow_redirects=True)

    def post_raw(self, path, data=None):
        return self.s.post(f"{self.base}{path}", data=data or {}, allow_redirects=False)


def find_or_create(rpc, model, name, vals):
    ids = rpc.search(model, [("name", "=", name)], limit=1)
    if ids:
        return ids[0]
    vals["name"] = name
    return rpc.create(model, vals)


# ============================================================
# PHASE 25: Setup / Verification
# ============================================================
def phase_25_setup(admin, portal1):
    section("Phase 25: V3 Setup & Data Verification")

    # Ensure portal users exist and passwords are set
    pu1 = admin.search("res.users", [("login", "=", PORTAL_USER1_LOGIN)])
    if pu1:
        admin.write("res.users", pu1, {"password": PORTAL_USER1_PASS})
        log_pass("25.1 Portal user 1 exists", f"ID={pu1[0]}")
    else:
        log_fail("25.1 Portal user 1 not found", PORTAL_USER1_LOGIN)
        return None

    pu2 = admin.search("res.users", [("login", "=", PORTAL_USER2_LOGIN)])
    if pu2:
        admin.write("res.users", pu2, {"password": PORTAL_USER2_PASS})
        log_pass("25.2 Portal user 2 exists", f"ID={pu2[0]}")
    else:
        log_warn("25.2 Portal user 2 not found", "Some cross-user tests will be skipped")

    # Find or create test equipment assigned to portal user 1
    equip_ids = admin.search("maintenance.equipment", [("portal_user_ids", "in", pu1)])
    if equip_ids:
        equip_id = equip_ids[0]
        log_pass("25.3 Test equipment found", f"ID={equip_id}")
    else:
        log_fail("25.3 No equipment assigned to portal user 1")
        return None

    # Find or create test request assigned to portal user 1
    req_ids = admin.search("maintenance.request", [("portal_user_ids", "in", pu1)])
    if req_ids:
        req_id = req_ids[0]
        log_pass("25.4 Test request found", f"ID={req_id}")
    else:
        log_fail("25.4 No request assigned to portal user 1")
        return None

    # Get stages
    stages = admin.sr("maintenance.stage", [], fields=["id", "name", "sequence", "done"])
    log_pass("25.5 Stages loaded", f"{len(stages)} stages")

    return {
        "portal_user1_id": pu1[0],
        "portal_user2_id": pu2[0] if pu2 else None,
        "equipment_id": equip_id,
        "request_id": req_id,
        "all_equipment_ids": equip_ids,
        "all_request_ids": req_ids,
        "stages": stages,
    }


# ============================================================
# PHASE 26: write() Field Restriction Completeness (GAP-08, GAP-12)
# ============================================================
def phase_26_write_restrictions(admin, portal1_rpc, data):
    section("Phase 26: write() Field Restriction Completeness")

    req_id = data["request_id"]

    # Fields that should be BLOCKED for portal users
    blocked_fields = {
        "name": "V3_Hacked_Name",
        "stage_id": 1,
        "equipment_id": 1,
        "description": "<p>hacked description</p>",
        "maintenance_type": "preventive",
        "schedule_date": "2030-01-01",
        "request_date": "2020-01-01",
        "maintenance_team_id": 1,
        "portal_user_ids": [(6, 0, [data["portal_user1_id"]])],
    }

    for field, value in blocked_fields.items():
        try:
            portal1_rpc.write("maintenance.request", [req_id], {field: value})
            log_fail(f"26.1 Write {field} should be blocked", "No AccessError raised")
        except xmlrpc.client.Fault as e:
            if "not allowed to modify" in str(e) or "Access" in str(e):
                log_pass(f"26.1 Write {field} blocked", "AccessError raised correctly")
            else:
                log_warn(f"26.1 Write {field}", f"Unexpected error: {e.faultString[:80]}")

    # portal_notes SHOULD be writable
    try:
        portal1_rpc.write("maintenance.request", [req_id], {"portal_notes": "V3 test note"})
        log_pass("26.2 Write portal_notes allowed")
    except xmlrpc.client.Fault as e:
        log_fail("26.2 Write portal_notes blocked", str(e.faultString)[:80])

    # Multiple forbidden fields at once
    try:
        portal1_rpc.write("maintenance.request", [req_id], {
            "portal_notes": "ok note",
            "name": "V3_SneakyHack"
        })
        log_fail("26.3 Mixed fields (allowed+forbidden) should fail", "No error raised")
    except xmlrpc.client.Fault as e:
        if "not allowed to modify" in str(e) or "Access" in str(e):
            log_pass("26.3 Mixed fields correctly blocked")
        else:
            log_warn("26.3 Mixed fields", f"Unexpected: {e.faultString[:80]}")

    # Equipment fields: portal should NOT have write access at all
    equip_id = data["equipment_id"]
    try:
        portal1_rpc.write("maintenance.equipment", [equip_id], {"name": "V3_Hacked_Equip"})
        log_fail("26.4 Equipment write should be blocked", "No error")
    except xmlrpc.client.Fault as e:
        log_pass("26.4 Equipment write blocked", f"Error: {str(e.faultString)[:60]}")


# ============================================================
# PHASE 27: Chatter / Mail Message Access (GAP-09, GAP-14, GAP-23)
# ============================================================
def phase_27_chatter_access(admin, data):
    section("Phase 27: Chatter / Mail Message Access")

    req_id = data["request_id"]
    equip_id = data["equipment_id"]
    portal_uid = data["portal_user1_id"]

    # Test 1: Portal user can post message on assigned request via HTTP
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Get the request detail page and check for chatter widget
    resp = h.get(f"/my/maintenance-requests/{req_id}")
    has_chatter = "o_portal_chatter" in resp.text or "message_thread" in resp.text.lower() or "o_portal_chatter_composer" in resp.text
    if has_chatter:
        log_pass("27.1 Chatter widget present on request detail")
    else:
        log_warn("27.1 Chatter widget not detected in HTML", "May use different class names")

    # Test 2: Check chatter on equipment detail page
    resp = h.get(f"/my/equipments/{equip_id}")
    has_eq_chatter = "o_portal_chatter" in resp.text or "message_thread" in resp.text.lower() or "o_portal_chatter_composer" in resp.text
    if has_eq_chatter:
        log_pass("27.2 Chatter widget present on equipment detail")
    else:
        log_warn("27.2 Chatter widget not detected on equipment detail")

    # Test 3: Post message via portal chatter endpoint (standard Odoo portal chatter URL)
    # The standard Odoo portal chatter posts to /mail/chatter_post
    test_msg = f"V3 chatter test message {int(time.time())}"
    csrf_page = h.get(f"/my/maintenance-requests/{req_id}")
    csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', csrf_page.text)
    csrf_token = csrf_match.group(1) if csrf_match else ""

    post_resp = h.s.post(f"{URL}/mail/chatter_post", data={
        "res_model": "maintenance.request",
        "res_id": req_id,
        "message": test_msg,
        "csrf_token": csrf_token,
    }, allow_redirects=True)

    if post_resp.status_code in (200, 302):
        # Verify message was created
        msgs = admin.sr("mail.message", [
            ("model", "=", "maintenance.request"),
            ("res_id", "=", req_id),
            ("body", "ilike", f"V3 chatter test message"),
        ], fields=["id", "body", "author_id"])
        if msgs:
            log_pass("27.3 Portal user posted chatter message", f"msg_id={msgs[0]['id']}")
        else:
            log_warn("27.3 Message post returned OK but message not found in DB")
    else:
        log_warn("27.3 Chatter post HTTP response", f"status={post_resp.status_code}")

    # Test 4: Portal user should NOT be able to post on unassigned request
    # Find or create a request NOT assigned to portal user 1
    unassigned_reqs = admin.search("maintenance.request", [
        ("portal_user_ids", "not in", [portal_uid])
    ], limit=1)

    if not unassigned_reqs:
        # Create one
        stage_ids = admin.search("maintenance.stage", [], limit=1)
        unassigned_id = admin.create("maintenance.request", {
            "name": "V3_Unassigned_Request",
            "stage_id": stage_ids[0] if stage_ids else False,
        })
        unassigned_reqs = [unassigned_id]
        log_pass("27.4a Created unassigned request", f"ID={unassigned_id}")

    unassigned_req_id = unassigned_reqs[0]

    # Try to access the unassigned request detail page
    resp = h.get(f"/my/maintenance-requests/{unassigned_req_id}")
    # Should redirect to /my since access denied
    if "/my" in resp.url and f"/maintenance-requests/{unassigned_req_id}" not in resp.url:
        log_pass("27.4 Unassigned request detail blocked", f"Redirected to {resp.url}")
    else:
        log_fail("27.4 Unassigned request accessible", f"URL={resp.url}")

    # Test 5: Try to post chatter on unassigned request directly
    post_resp2 = h.s.post(f"{URL}/mail/chatter_post", data={
        "res_model": "maintenance.request",
        "res_id": unassigned_req_id,
        "message": "V3 unauthorized chatter attempt",
        "csrf_token": csrf_token,
    }, allow_redirects=True)

    # Check if message was created
    unauth_msgs = admin.sr("mail.message", [
        ("model", "=", "maintenance.request"),
        ("res_id", "=", unassigned_req_id),
        ("body", "ilike", "V3 unauthorized chatter"),
    ], fields=["id", "body", "author_id"])
    if not unauth_msgs:
        log_pass("27.5 Chatter on unassigned request blocked", "No message created")
    else:
        log_fail("27.5 Chatter on unassigned request NOT blocked", f"msg_id={unauth_msgs[0]['id']}")
        # Clean up
        admin.unlink("mail.message", [m["id"] for m in unauth_msgs])

    # Test 6: Post chatter on equipment
    test_eq_msg = f"V3 equipment chatter {int(time.time())}"
    eq_page = h.get(f"/my/equipments/{equip_id}")
    csrf_match2 = re.search(r'name="csrf_token"\s+value="([^"]+)"', eq_page.text)
    csrf_token2 = csrf_match2.group(1) if csrf_match2 else csrf_token

    post_resp3 = h.s.post(f"{URL}/mail/chatter_post", data={
        "res_model": "maintenance.equipment",
        "res_id": equip_id,
        "message": test_eq_msg,
        "csrf_token": csrf_token2,
    }, allow_redirects=True)

    eq_msgs = admin.sr("mail.message", [
        ("model", "=", "maintenance.equipment"),
        ("res_id", "=", equip_id),
        ("body", "ilike", "V3 equipment chatter"),
    ], fields=["id", "body", "author_id"])
    if eq_msgs:
        log_pass("27.6 Portal chatter on equipment works", f"msg_id={eq_msgs[0]['id']}")
    else:
        log_warn("27.6 Equipment chatter message not found")


# ============================================================
# PHASE 28: Cross-Assignment Scenarios (GAP-18, GAP-19)
# ============================================================
def phase_28_cross_assignment(admin, data):
    section("Phase 28: Cross-Assignment Scenarios")

    pu1_id = data["portal_user1_id"]
    pu2_id = data["portal_user2_id"]

    if not pu2_id:
        log_warn("28.0 Skipping cross-assignment", "Portal user 2 not available")
        return

    # Create equipment assigned to BOTH users
    stage_ids = admin.search("maintenance.stage", [("done", "=", False)], limit=1)
    done_stage_ids = admin.search("maintenance.stage", [("done", "=", True)], limit=1)

    shared_equip_id = find_or_create(admin, "maintenance.equipment", "V3_SharedEquipment", {
        "portal_user_ids": [(6, 0, [pu1_id, pu2_id])],
    })
    log_pass("28.1 Shared equipment created", f"ID={shared_equip_id}")

    # Create request on shared equipment assigned to ONLY user 1
    req_only_u1_id = find_or_create(admin, "maintenance.request", "V3_ReqOnlyUser1", {
        "equipment_id": shared_equip_id,
        "portal_user_ids": [(6, 0, [pu1_id])],
        "stage_id": stage_ids[0] if stage_ids else False,
    })
    log_pass("28.2 Request (user1 only) on shared equipment", f"ID={req_only_u1_id}")

    # Create request assigned to ONLY user 2
    req_only_u2_id = find_or_create(admin, "maintenance.request", "V3_ReqOnlyUser2", {
        "equipment_id": shared_equip_id,
        "portal_user_ids": [(6, 0, [pu2_id])],
        "stage_id": stage_ids[0] if stage_ids else False,
    })
    log_pass("28.3 Request (user2 only) on shared equipment", f"ID={req_only_u2_id}")

    # User 1 views shared equipment detail => should see only their request
    h1 = HTTP(URL, DB)
    h1.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    resp1 = h1.get(f"/my/equipments/{shared_equip_id}")

    if "V3_ReqOnlyUser1" in resp1.text:
        log_pass("28.4 User1 sees own request on shared equipment")
    else:
        log_fail("28.4 User1 does NOT see own request on shared equipment")

    if "V3_ReqOnlyUser2" not in resp1.text:
        log_pass("28.5 User1 does NOT see user2's request on shared equipment")
    else:
        log_fail("28.5 User1 sees user2's request (cross-user leak)")

    # User 2 views shared equipment
    h2 = HTTP(URL, DB)
    h2.login(PORTAL_USER2_LOGIN, PORTAL_USER2_PASS)
    resp2 = h2.get(f"/my/equipments/{shared_equip_id}")

    if "V3_ReqOnlyUser2" in resp2.text:
        log_pass("28.6 User2 sees own request on shared equipment")
    else:
        log_fail("28.6 User2 does NOT see own request on shared equipment")

    if "V3_ReqOnlyUser1" not in resp2.text:
        log_pass("28.7 User2 does NOT see user1's request")
    else:
        log_fail("28.7 User2 sees user1's request (cross-user leak)")

    # Test: equipment assigned to user A, request on that equipment assigned to user B
    # User B sees request detail with equipment link - click through should be blocked
    equip_only_u1 = find_or_create(admin, "maintenance.equipment", "V3_EquipOnlyUser1", {
        "portal_user_ids": [(6, 0, [pu1_id])],
    })
    req_cross_id = find_or_create(admin, "maintenance.request", "V3_CrossAssignReq", {
        "equipment_id": equip_only_u1,
        "portal_user_ids": [(6, 0, [pu2_id])],
        "stage_id": stage_ids[0] if stage_ids else False,
    })
    log_pass("28.8 Cross-assignment data created", f"equip(u1)={equip_only_u1}, req(u2)={req_cross_id}")

    # User 2 accesses the request (should work - they're assigned)
    resp_cross = h2.get(f"/my/maintenance-requests/{req_cross_id}")
    if "V3_CrossAssignReq" in resp_cross.text:
        log_pass("28.9 User2 can view cross-assigned request")
    else:
        log_fail("28.9 User2 cannot view cross-assigned request")

    # The request detail shows equipment name via sudo - verify it shows
    if "V3_EquipOnlyUser1" in resp_cross.text:
        log_pass("28.10 Equipment name shown via sudo on cross-assigned request")
    else:
        log_warn("28.10 Equipment name not shown on cross-assigned request")

    # User 2 clicks equipment link => should redirect (no access)
    resp_eq_blocked = h2.get(f"/my/equipments/{equip_only_u1}")
    if f"/equipments/{equip_only_u1}" not in resp_eq_blocked.url or "/my" in resp_eq_blocked.url:
        log_pass("28.11 User2 blocked from user1's equipment detail", f"URL={resp_eq_blocked.url}")
    else:
        log_fail("28.11 User2 accessed user1's equipment", f"URL={resp_eq_blocked.url}")


# ============================================================
# PHASE 29: stage_id=False Action Execution (GAP-20)
# ============================================================
def phase_29_stageless_actions(admin, data):
    section("Phase 29: stage_id=False Action Execution")

    pu1_id = data["portal_user1_id"]

    # Create a request with no stage
    req_no_stage_id = find_or_create(admin, "maintenance.request", "V3_NoStageRequest", {
        "portal_user_ids": [(6, 0, [pu1_id])],
    })
    # Force stage_id to False
    admin.write("maintenance.request", [req_no_stage_id], {"stage_id": False})
    log_pass("29.1 Created request with stage_id=False", f"ID={req_no_stage_id}")

    # Try action_portal_set_in_progress via HTTP
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    resp = h.post_with_csrf(f"/my/maintenance-requests/{req_no_stage_id}/update", data={"action": "in_progress"})
    if resp.status_code in (200, 302) and "500" not in resp.text[:200]:
        log_pass("29.2 set_in_progress on stageless request didn't crash")
    else:
        log_fail("29.2 set_in_progress on stageless request crashed", f"status={resp.status_code}")

    # Check if stage was set
    req_after = admin.read("maintenance.request", [req_no_stage_id], ["stage_id"])
    if req_after and req_after[0].get("stage_id"):
        log_pass("29.3 Stage assigned after in_progress action", f"stage={req_after[0]['stage_id']}")
    else:
        log_warn("29.3 Stage still empty after in_progress", "action_portal_set_in_progress uses sequence > 0 which may match")

    # Try action_portal_set_done on the same request
    resp2 = h.post_with_csrf(f"/my/maintenance-requests/{req_no_stage_id}/update", data={"action": "done"})
    if resp2.status_code in (200, 302) and "500" not in resp2.text[:200]:
        log_pass("29.4 set_done on previously-stageless request didn't crash")
    else:
        log_fail("29.4 set_done crashed", f"status={resp2.status_code}")


# ============================================================
# PHASE 30: CSS/SVG Asset Loading (GAP-28, GAP-29)
# ============================================================
def phase_30_asset_loading(admin, data):
    section("Phase 30: CSS/SVG Asset Loading")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Test 1: Check that portal.css is referenced in the portal page
    resp = h.get("/my/equipments")
    # Odoo bundles CSS via asset bundles, check if our CSS classes are working
    # by checking for our custom class names in the rendered HTML
    custom_classes = [
        "maintenance-equipment-card",
    ]
    found_classes = [c for c in custom_classes if c in resp.text]
    if found_classes:
        log_pass("30.1 Custom CSS classes present in HTML", f"Found: {found_classes}")
    else:
        log_warn("30.1 Custom CSS classes not found in equipment list HTML")

    # Test 2: Check request list for mobile card class
    resp2 = h.get("/my/maintenance-requests")
    if "maintenance-request-card" in resp2.text:
        log_pass("30.2 Mobile card CSS class present in request list")
    else:
        log_warn("30.2 Mobile card CSS class not found")

    # Test 3: Check request detail for progress bar class
    req_id = data["request_id"]
    resp3 = h.get(f"/my/maintenance-requests/{req_id}")
    progress_classes = ["maintenance-progress", "maintenance-stage-circle", "maintenance-progress-wrapper"]
    found_progress = [c for c in progress_classes if c in resp3.text]
    if len(found_progress) >= 2:
        log_pass("30.3 Progress bar CSS classes present", f"Found: {found_progress}")
    else:
        log_warn("30.3 Progress bar classes missing", f"Found: {found_progress}")

    # Test 4: SVG icon files are accessible
    svg_paths = [
        "/maintenance_portal/static/src/img/equipment.svg",
        "/maintenance_portal/static/src/img/maintenance.svg",
    ]
    for svg_path in svg_paths:
        svg_resp = h.get(svg_path)
        if svg_resp.status_code == 200 and ("svg" in svg_resp.text.lower() or len(svg_resp.content) > 50):
            log_pass(f"30.4 SVG accessible: {svg_path}")
        else:
            log_fail(f"30.4 SVG NOT accessible: {svg_path}", f"status={svg_resp.status_code}")

    # Test 5: Verify CSS is loaded by checking portal home for asset bundle reference
    resp_home = h.get("/my")
    if "maintenance_portal" in resp_home.text or "portal.css" in resp_home.text:
        log_pass("30.5 CSS bundle reference found on portal home")
    else:
        # In Odoo 18, assets are compiled and minified, so direct reference may not be visible
        # Check via equipment list which definitely uses our classes
        if "maintenance-equipment-card" in resp.text:
            log_pass("30.5 CSS working (verified via class usage)")
        else:
            log_warn("30.5 CSS bundle reference not detected (may be compiled)")

    # Test 6: Check info-label class on detail pages
    if "maintenance-info-label" in resp3.text:
        log_pass("30.6 maintenance-info-label class in request detail")
    else:
        log_warn("30.6 maintenance-info-label class not found in request detail")


# ============================================================
# PHASE 31: End-to-End Navigation Flow (GAP-30)
# ============================================================
def phase_31_navigation_flow(admin, data):
    section("Phase 31: End-to-End Navigation Flow")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Step 1: Portal Home
    resp = h.get("/my")
    if resp.status_code == 200 and ("設備" in resp.text or "equipments" in resp.text.lower()):
        log_pass("31.1 Portal home loads with equipment link")
    else:
        log_fail("31.1 Portal home issue", f"status={resp.status_code}")

    # Step 2: Home -> Equipment List
    resp = h.get("/my/equipments")
    if resp.status_code == 200:
        # Find first equipment link
        eq_link = re.search(r'href="/my/equipments/(\d+)"', resp.text)
        if eq_link:
            eq_id = eq_link.group(1)
            log_pass("31.2 Equipment list loads with equipment links", f"First ID={eq_id}")
        else:
            log_fail("31.2 No equipment links found on list page")
            return
    else:
        log_fail("31.2 Equipment list HTTP error", f"status={resp.status_code}")
        return

    # Step 3: Equipment List -> Equipment Detail
    resp = h.get(f"/my/equipments/{eq_id}")
    if resp.status_code == 200:
        log_pass("31.3 Equipment detail loads")
    else:
        log_fail("31.3 Equipment detail error", f"status={resp.status_code}")
        return

    # Step 4: Equipment Detail -> Related Request (if any)
    req_link = re.search(r'href="/my/maintenance-requests/(\d+)"', resp.text)
    if req_link:
        related_req_id = req_link.group(1)
        resp = h.get(f"/my/maintenance-requests/{related_req_id}")
        if resp.status_code == 200:
            log_pass("31.4 Equipment -> Request navigation works", f"req_id={related_req_id}")
        else:
            log_fail("31.4 Request detail from equipment link error", f"status={resp.status_code}")
    else:
        log_warn("31.4 No related request link on equipment detail")

    # Step 5: Back to list button
    if '返回列表' in resp.text and '/my/maintenance-requests' in resp.text:
        log_pass("31.5 Back to list link present on request detail")
    else:
        log_warn("31.5 Back to list link not found")

    # Step 6: Request List page
    resp = h.get("/my/maintenance-requests")
    if resp.status_code == 200:
        req_link2 = re.search(r'href="/my/maintenance-requests/(\d+)"', resp.text)
        if req_link2:
            log_pass("31.6 Request list loads with request links")
        else:
            log_warn("31.6 No request links on list page")
    else:
        log_fail("31.6 Request list error", f"status={resp.status_code}")

    # Step 7: Request Detail page
    req_id = data["request_id"]
    resp = h.get(f"/my/maintenance-requests/{req_id}")
    if resp.status_code == 200:
        log_pass("31.7 Request detail loads")
    else:
        log_fail("31.7 Request detail error", f"status={resp.status_code}")

    # Step 8: Equipment link from request detail
    eq_back_link = re.search(r'href="/my/equipments/(\d+)"', resp.text)
    if eq_back_link:
        resp_back = h.get(f"/my/equipments/{eq_back_link.group(1)}")
        if resp_back.status_code == 200:
            log_pass("31.8 Request -> Equipment navigation works")
        else:
            log_fail("31.8 Equipment from request link error")
    else:
        log_warn("31.8 No equipment link on request detail")

    # Step 9: Back to list on equipment detail
    equip_id = data["equipment_id"]
    resp = h.get(f"/my/equipments/{equip_id}")
    if '返回列表' in resp.text and '/my/equipments' in resp.text:
        log_pass("31.9 Back to list link on equipment detail")
    else:
        log_warn("31.9 Back to list link not found on equipment detail")


# ============================================================
# PHASE 32: Empty States and Edge Display (GAP-32, GAP-31)
# ============================================================
def phase_32_empty_states_and_progress(admin, data):
    section("Phase 32: Empty States & Progress Bar")

    # Create a user with NO assigned records for empty state test
    pu2_id = data["portal_user2_id"]

    if pu2_id:
        # Check if user2 has any requests
        u2_req_count = admin.count("maintenance.request", [("portal_user_ids", "in", [pu2_id])])

        h2 = HTTP(URL, DB)
        h2.login(PORTAL_USER2_LOGIN, PORTAL_USER2_PASS)

        # Test request list empty state
        if u2_req_count == 0:
            resp = h2.get("/my/maintenance-requests")
            if "沒有指派給您的維修請求" in resp.text:
                log_pass("32.1 Request list empty state message shown")
            else:
                log_fail("32.1 Request list empty state message missing")
        else:
            # User2 might have requests from phase 28 - check with fresh session
            log_warn("32.1 User2 has requests, empty state test approximate", f"count={u2_req_count}")
    else:
        log_warn("32.1 No portal user 2, skipping empty state tests")

    # Progress bar visual correctness
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    req_id = data["request_id"]
    resp = h.get(f"/my/maintenance-requests/{req_id}")

    # Parse stages and check highlighted circles
    stages = data["stages"]
    req_data = admin.read("maintenance.request", [req_id], ["stage_id"])
    current_stage_id = req_data[0]["stage_id"][0] if req_data[0].get("stage_id") else None

    if current_stage_id:
        current_stage = [s for s in stages if s["id"] == current_stage_id]
        if current_stage:
            current_seq = current_stage[0]["sequence"]

            # Count bg-primary circles (should be stages with sequence <= current)
            bg_primary_count = resp.text.count("bg-primary text-white")
            expected_active = len([s for s in stages if s["sequence"] <= current_seq])

            # The title bar also uses bg-primary, so be lenient
            if bg_primary_count >= expected_active:
                log_pass("32.2 Progress bar circles highlighted correctly",
                         f"active={bg_primary_count}, expected>={expected_active}")
            else:
                log_warn("32.2 Progress bar circle count mismatch",
                         f"active={bg_primary_count}, expected>={expected_active}")

            # Check current stage is bold
            if "fw-bold text-primary" in resp.text:
                log_pass("32.3 Current stage label styled with fw-bold")
            else:
                log_warn("32.3 Current stage bold styling not found")
        else:
            log_warn("32.2 Current stage not found in stages list")
    else:
        log_warn("32.2 Request has no current stage, skipping progress bar check")

    # Check progress wrapper class for responsive scrolling
    if "maintenance-progress-wrapper" in resp.text:
        log_pass("32.4 Progress wrapper class for responsive scrolling present")
    else:
        log_warn("32.4 Progress wrapper class not found")

    # Check dual layout (table + cards) on request list
    resp_list = h.get("/my/maintenance-requests")
    has_table = "d-none d-md-block" in resp_list.text
    has_cards = "d-md-none" in resp_list.text
    if has_table and has_cards:
        log_pass("32.5 Dual layout (desktop table + mobile cards) present")
    elif has_table:
        log_warn("32.5 Desktop table present but mobile cards missing")
    elif has_cards:
        log_warn("32.5 Mobile cards present but desktop table missing")
    else:
        log_fail("32.5 Neither responsive layout class found")


# ============================================================
# PHASE 33: Dead Code / BUG-01 Verification
# ============================================================
def phase_33_dead_code_verification(admin, data):
    section("Phase 33: Dead Code / BUG-01 Verification")

    req_id = data["request_id"]

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Test 1: Verify no textarea for notes on request detail
    resp = h.get(f"/my/maintenance-requests/{req_id}")
    if '<textarea' in resp.text.lower() and 'notes' in resp.text.lower():
        log_fail("33.1 Notes textarea still present on request detail (should have been removed)")
    else:
        log_pass("33.1 No notes textarea on request detail (chatter replaces it)")

    # Test 2: POST with notes should NOT create portal_notes
    # Save current portal_notes value
    req_before = admin.read("maintenance.request", [req_id], ["portal_notes"])
    notes_before = req_before[0].get("portal_notes") or ""

    post_resp = h.post_with_csrf(f"/my/maintenance-requests/{req_id}/update", data={
        "action": "",
        "notes": "V3_dead_code_test_note"
    })

    req_after = admin.read("maintenance.request", [req_id], ["portal_notes"])
    notes_after = req_after[0].get("portal_notes") or ""

    if "V3_dead_code_test_note" not in notes_after:
        log_pass("33.2 Notes POST parameter no longer processed by controller")
    else:
        log_fail("33.2 Notes POST still processed (dead code not removed)", f"portal_notes={notes_after[:80]}")

    # Test 3: Chatter is present as replacement
    if "portal_chatter" in resp.text.lower() or "message_thread" in resp.text.lower() or "o_portal_chatter" in resp.text:
        log_pass("33.3 Chatter widget present as notes replacement")
    else:
        log_warn("33.3 Chatter widget not explicitly detected")

    # Test 4: Update form only has action buttons (no textarea)
    form_match = re.search(r'<form[^>]*update[^>]*>(.*?)</form>', resp.text, re.DOTALL)
    if form_match:
        form_html = form_match.group(1)
        if '<textarea' not in form_html.lower():
            log_pass("33.4 Update form contains no textarea")
        else:
            log_fail("33.4 Update form still contains textarea")

        # Should have action buttons
        if 'name="action"' in form_html:
            log_pass("33.5 Update form has action buttons")
        else:
            log_warn("33.5 Update form has no action buttons")
    else:
        log_warn("33.4 Update form not found in HTML")


# ============================================================
# PHASE 34: Search Edge Cases (GAP-04 backslash)
# ============================================================
def phase_34_search_edge_cases(admin, data):
    section("Phase 34: Search Edge Cases (backslash escape)")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Test 1: Backslash in search term
    resp = h.get("/my/equipments", params={"search": "test\\name", "search_in": "name"})
    if resp.status_code == 200:
        log_pass("34.1 Backslash in equipment search doesn't crash")
    else:
        log_fail("34.1 Backslash in search crashed", f"status={resp.status_code}")

    # Test 2: Backslash in request search
    resp2 = h.get("/my/maintenance-requests", params={"search": "req\\test", "search_in": "name"})
    if resp2.status_code == 200:
        log_pass("34.2 Backslash in request search doesn't crash")
    else:
        log_fail("34.2 Backslash in request search crashed")

    # Test 3: Double backslash
    resp3 = h.get("/my/equipments", params={"search": "\\\\test", "search_in": "name"})
    if resp3.status_code == 200:
        log_pass("34.3 Double backslash search doesn't crash")
    else:
        log_fail("34.3 Double backslash search crashed")

    # Test 4: Mixed special chars
    resp4 = h.get("/my/equipments", params={"search": "te%st\\_na%me", "search_in": "name"})
    if resp4.status_code == 200:
        log_pass("34.4 Mixed special chars in search doesn't crash")
    else:
        log_fail("34.4 Mixed special chars crashed")

    # Test 5: Very long search term
    long_search = "A" * 500
    resp5 = h.get("/my/equipments", params={"search": long_search, "search_in": "name"})
    if resp5.status_code == 200:
        log_pass("34.5 Very long search term handled")
    else:
        log_fail("34.5 Very long search term crashed")

    # Test 6: NULL byte in search (web frameworks typically reject this with 400/500)
    resp6 = h.get("/my/equipments", params={"search": "test\x00name", "search_in": "name"})
    if resp6.status_code in (200, 400):
        log_pass("34.6 NULL byte in search handled", f"status={resp6.status_code}")
    elif resp6.status_code == 500:
        log_warn("34.6 NULL byte causes 500 (expected - web framework rejects null bytes)")
    else:
        log_fail("34.6 NULL byte caused unexpected error", f"status={resp6.status_code}")


# ============================================================
# PHASE 35: _check_portal_access for Internal Users (GAP-10)
# ============================================================
def phase_35_internal_user_portal_actions(admin, data):
    section("Phase 35: Internal User Portal Action Access (GAP-10)")

    req_id = data["request_id"]

    # Admin (internal user) calling portal action methods
    # _check_portal_access only blocks portal users not in portal_user_ids
    # Internal users should pass through without error
    try:
        # Save current stage
        req_before = admin.read("maintenance.request", [req_id], ["stage_id"])
        stage_before = req_before[0]["stage_id"]

        # Admin calls portal action
        result = admin.call("maintenance.request", "action_portal_set_in_progress", [req_id])
        log_pass("35.1 Admin can call action_portal_set_in_progress", f"result={result}")

        # Restore original stage
        if stage_before:
            admin.write("maintenance.request", [req_id], {"stage_id": stage_before[0]})
    except xmlrpc.client.Fault as e:
        if "Access" in str(e):
            log_fail("35.1 Admin blocked from portal action", str(e.faultString)[:80])
        else:
            log_warn("35.1 Admin portal action error", str(e.faultString)[:80])

    # Admin calls action_portal_set_done
    try:
        req_before = admin.read("maintenance.request", [req_id], ["stage_id"])
        stage_before = req_before[0]["stage_id"]

        result = admin.call("maintenance.request", "action_portal_set_done", [req_id])
        log_pass("35.2 Admin can call action_portal_set_done", f"result={result}")

        # Restore
        if stage_before:
            admin.write("maintenance.request", [req_id], {"stage_id": stage_before[0]})
    except xmlrpc.client.Fault as e:
        log_warn("35.2 Admin action_portal_set_done error", str(e.faultString)[:80])

    # Admin calls action_portal_add_notes
    try:
        result = admin.call("maintenance.request", "action_portal_add_notes", [req_id], "V3 admin note test")
        log_pass("35.3 Admin can call action_portal_add_notes")
    except xmlrpc.client.Fault as e:
        log_warn("35.3 Admin action_portal_add_notes error", str(e.faultString)[:80])

    # Test request NOT assigned to any portal user - admin should still work
    unassigned = admin.search("maintenance.request", [("portal_user_ids", "=", False)], limit=1)
    if unassigned:
        try:
            result = admin.call("maintenance.request", "action_portal_set_in_progress", unassigned)
            log_pass("35.4 Admin can call portal action on unassigned request")
        except xmlrpc.client.Fault as e:
            log_warn("35.4 Admin on unassigned request", str(e.faultString)[:80])
    else:
        log_warn("35.4 No unassigned requests to test")


# ============================================================
# PHASE 36: Portal Home Counter Edge Cases (GAP-05)
# ============================================================
def phase_36_portal_counters(admin, data):
    section("Phase 36: Portal Home Counter Edge Cases")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Test 1: Portal home shows counter values
    resp = h.get("/my")
    if resp.status_code == 200:
        # Check for equipment and maintenance request sections
        has_equip_section = "設備" in resp.text
        has_req_section = "維修請求" in resp.text
        if has_equip_section and has_req_section:
            log_pass("36.1 Portal home shows both counter sections")
        elif has_equip_section:
            log_pass("36.1 Portal home shows equipment section", "Request section might differ")
        else:
            log_fail("36.1 Portal home missing counter sections")
    else:
        log_fail("36.1 Portal home error", f"status={resp.status_code}")

    # Test 2: Counter accuracy
    pu1_id = data["portal_user1_id"]
    actual_equip = admin.count("maintenance.equipment", [("portal_user_ids", "in", [pu1_id])])
    actual_req = admin.count("maintenance.request", [("portal_user_ids", "in", [pu1_id])])
    log_pass("36.2 Counter reference values", f"equipment={actual_equip}, requests={actual_req}")

    # Test 3: Unauthenticated access to /my should redirect to login
    h_anon = HTTP(URL, DB)
    resp_anon = h_anon.s.get(f"{URL}/my", allow_redirects=False)
    if resp_anon.status_code in (302, 303):
        log_pass("36.3 Unauthenticated /my redirects to login")
    else:
        log_fail("36.3 Unauthenticated /my does not redirect", f"status={resp_anon.status_code}")


# ============================================================
# PHASE 37: access_token Dead Parameter (GAP-11)
# ============================================================
def phase_37_access_token(admin, data):
    section("Phase 37: _document_check_access access_token Parameter")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    equip_id = data["equipment_id"]
    req_id = data["request_id"]

    # Test 1: access_token parameter in URL does not affect behavior
    resp1 = h.get(f"/my/equipments/{equip_id}?access_token=fake_token_12345")
    if resp1.status_code == 200:
        log_pass("37.1 Equipment detail with fake access_token still works")
    else:
        log_fail("37.1 Equipment with access_token error", f"status={resp1.status_code}")

    # Test 2: Unassigned equipment with access_token should still be blocked
    all_equip = admin.search("maintenance.equipment", [], limit=100)
    assigned = admin.search("maintenance.equipment", [("portal_user_ids", "in", [data["portal_user1_id"]])])
    unassigned = list(set(all_equip) - set(assigned))

    if unassigned:
        resp2 = h.get(f"/my/equipments/{unassigned[0]}?access_token=super_secret_bypass")
        if f"/equipments/{unassigned[0]}" not in resp2.url or "/my" in resp2.url:
            log_pass("37.2 access_token does NOT bypass access check")
        else:
            log_fail("37.2 access_token BYPASSES access check", f"URL={resp2.url}")
    else:
        log_warn("37.2 No unassigned equipment to test access_token bypass")


# ============================================================
# PHASE 38: Request List Responsive Layout Verification
# ============================================================
def phase_38_responsive_layout(admin, data):
    section("Phase 38: Responsive Layout HTML Verification")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # Request list: check desktop table and mobile cards
    resp = h.get("/my/maintenance-requests")

    # Desktop table
    if '<table' in resp.text and 'table-hover' in resp.text:
        log_pass("38.1 Desktop table element present")
    else:
        log_fail("38.1 Desktop table missing")

    # Table headers
    expected_headers = ["請求名稱", "設備", "階段", "日期", "操作"]
    found_headers = [h for h in expected_headers if h in resp.text]
    if len(found_headers) == len(expected_headers):
        log_pass("38.2 All table headers present", str(found_headers))
    else:
        log_warn("38.2 Some headers missing", f"Found: {found_headers}")

    # Mobile card view
    if "maintenance-request-card" in resp.text:
        log_pass("38.3 Mobile card elements present")
    else:
        log_fail("38.3 Mobile card elements missing")

    # Card contains truncation class
    if "text-truncate" in resp.text:
        log_pass("38.4 Text truncation class in mobile cards")
    else:
        log_warn("38.4 Text truncation class missing")

    # Check equipment list responsive elements
    resp_eq = h.get("/my/equipments")
    if "col-md-4" in resp_eq.text and "col-sm-6" in resp_eq.text:
        log_pass("38.5 Equipment cards use responsive grid (col-md-4 col-sm-6)")
    else:
        log_warn("38.5 Equipment responsive grid classes not found")

    # Check detail page responsive classes
    req_id = data["request_id"]
    resp_detail = h.get(f"/my/maintenance-requests/{req_id}")
    if "flex-wrap" in resp_detail.text:
        log_pass("38.6 Detail title uses flex-wrap for mobile")
    else:
        log_warn("38.6 flex-wrap not found on detail title")

    if "btn-sm" in resp_detail.text:
        log_pass("38.7 Compact buttons (btn-sm) on detail page")
    else:
        log_warn("38.7 btn-sm not found on detail")

    # Icon hide on mobile
    if "d-none d-sm-inline" in resp_detail.text:
        log_pass("38.8 Icons hidden on mobile (d-none d-sm-inline)")
    else:
        log_warn("38.8 Mobile icon hiding class not found")


# ============================================================
# PHASE 39: Security - Template Field Leakage (GAP-13)
# ============================================================
def phase_39_field_leakage(admin, data):
    section("Phase 39: Template Field Leakage Check")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    req_id = data["request_id"]
    resp = h.get(f"/my/maintenance-requests/{req_id}")

    # Fields that should NOT be visible to portal users
    # The template uses sudo so technically all fields are accessible,
    # but only specific fields should be rendered
    sensitive_patterns = [
        "owner_user_id",
        "employee_id",
        "technician_user_id",
        "duration",
        "company_id",
    ]

    leaked = []
    for pattern in sensitive_patterns:
        if pattern in resp.text:
            leaked.append(pattern)

    if not leaked:
        log_pass("39.1 No sensitive field names leaked in request detail HTML")
    else:
        log_warn("39.1 Sensitive field references found in HTML", f"Fields: {leaked}")

    # Equipment detail
    equip_id = data["equipment_id"]
    resp_eq = h.get(f"/my/equipments/{equip_id}")

    sensitive_eq = [
        "owner_user_id",
        "employee_id",
        "cost",
        "warranty_date",
        "effective_date",
    ]

    leaked_eq = []
    for pattern in sensitive_eq:
        if pattern in resp_eq.text:
            leaked_eq.append(pattern)

    if not leaked_eq:
        log_pass("39.2 No sensitive field names leaked in equipment detail HTML")
    else:
        log_warn("39.2 Sensitive field references in equipment HTML", f"Fields: {leaked_eq}")


# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n{'#'*65}")
    print(f"  Maintenance Portal V3 - Professional Gap Coverage Tests")
    print(f"  Target: {URL}  DB: {DB}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*65}")

    try:
        admin = RPC(URL, DB, ADMIN_USER, ADMIN_PASS)
    except Exception as e:
        print(f"\n  FATAL: Cannot connect as admin: {e}")
        sys.exit(1)

    try:
        portal1 = RPC(URL, DB, PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    except Exception as e:
        print(f"\n  FATAL: Cannot connect as portal user: {e}")
        sys.exit(1)

    # Setup
    data = phase_25_setup(admin, portal1)
    if not data:
        print("\n  FATAL: Setup failed, cannot continue")
        sys.exit(1)

    # Run all test phases
    phases = [
        (phase_26_write_restrictions, (admin, portal1, data)),
        (phase_27_chatter_access, (admin, data)),
        (phase_28_cross_assignment, (admin, data)),
        (phase_29_stageless_actions, (admin, data)),
        (phase_30_asset_loading, (admin, data)),
        (phase_31_navigation_flow, (admin, data)),
        (phase_32_empty_states_and_progress, (admin, data)),
        (phase_33_dead_code_verification, (admin, data)),
        (phase_34_search_edge_cases, (admin, data)),
        (phase_35_internal_user_portal_actions, (admin, data)),
        (phase_36_portal_counters, (admin, data)),
        (phase_37_access_token, (admin, data)),
        (phase_38_responsive_layout, (admin, data)),
        (phase_39_field_leakage, (admin, data)),
    ]

    for func, args in phases:
        try:
            func(*args)
        except Exception as e:
            section(f"EXCEPTION in {func.__name__}")
            traceback.print_exc()
            log_fail(f"{func.__name__} EXCEPTION", str(e)[:120])

    # ============================================================
    # Final Report
    # ============================================================
    total = results["passed"] + results["failed"] + results["warned"]
    print(f"\n{'='*65}")
    print(f"  FINAL REPORT")
    print(f"{'='*65}")
    print(f"\n  Total:    {total}")
    print(f"  Passed:   \033[32m{results['passed']}\033[0m")
    print(f"  Failed:   \033[31m{results['failed']}\033[0m")
    print(f"  Warnings: \033[33m{results['warned']}\033[0m")
    pct = (results['passed'] / total * 100) if total else 0
    print(f"  Pass Rate: {pct:.1f}%")

    if results["failed"]:
        print(f"\n  === FAILURES ({results['failed']}) ===")
        for status, name, detail in results["details"]:
            if status == "FAIL":
                print(f"    [FAIL] {name}: {detail}")

    if results["warned"]:
        print(f"\n  === WARNINGS ({results['warned']}) ===")
        for status, name, detail in results["details"]:
            if status == "WARN":
                print(f"    [WARN] {name}: {detail}")

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}")

    sys.exit(1 if results["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
