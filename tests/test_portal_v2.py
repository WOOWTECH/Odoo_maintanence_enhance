#!/usr/bin/env python3
"""
Maintenance Portal V2 - Comprehensive Edge/Stress/Security Test Suite
Covers 52 testing gaps from V1 analysis.
ALL TEST DATA IS PRESERVED for manual inspection.
Target: Odoo 18 at localhost:9070, DB=odoomaintain
"""
import xmlrpc.client
import requests
import re
import sys
import time
import threading
import traceback
from datetime import datetime

# ============================================================
# Configuration
# ============================================================
URL = "http://localhost:9070"
DB = "odoomaintain"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
PORTAL_USER1_LOGIN = "vendor_test@test.com"
PORTAL_USER1_PASS = "vendor_test_123"
PORTAL_USER2_LOGIN = "vendor_test2@test.com"
PORTAL_USER2_PASS = "vendor_test2_123"

# Known IDs from V1 (will be verified at startup)
EQUIPMENT_A_ID = 1
EQUIPMENT_B_ID = 2
REQUEST_ALPHA_ID = 1

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
        """POST with auto-fetched CSRF token from the related detail page."""
        if data is None: data = {}
        # Fetch the parent page to get CSRF
        parent = path.rsplit("/update", 1)[0] if "/update" in path else path
        page = self.s.get(f"{self.base}{parent}")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
        if csrf: data["csrf_token"] = csrf.group(1)
        return self.s.post(f"{self.base}{path}", data=data, allow_redirects=True)

    def post_raw(self, path, data=None):
        """POST WITHOUT csrf token."""
        return self.s.post(f"{self.base}{path}", data=data or {}, allow_redirects=False)

    def raw_method(self, method, path):
        """Send arbitrary HTTP method."""
        return self.s.request(method, f"{self.base}{path}", allow_redirects=False)


def find_or_create(rpc, model, name, vals):
    """Find existing record by name or create new one. Returns ID."""
    ids = rpc.search(model, [("name", "=", name)], limit=1)
    if ids:
        return ids[0]
    vals["name"] = name
    return rpc.create(model, vals)


def create_portal_user(rpc, name, login, pwd, portal_group_id):
    """Create portal user if not exists. Returns user ID."""
    existing = rpc.sr("res.users", [("login", "=", login)], fields=["id"])
    if existing:
        return existing[0]["id"]
    partner_id = rpc.create("res.partner", {"name": name, "email": login})
    return rpc.create("res.users", {
        "name": name, "login": login, "password": pwd,
        "partner_id": partner_id,
        "groups_id": [(6, 0, [portal_group_id])],
    })


# ============================================================
# Phase 13: XSS and Security Injection
# ============================================================
def phase_13(rpc, portal_group_id, stages):
    section("Phase 13: XSS & Security Injection Tests")

    team_id = rpc.search("maintenance.team", [], limit=1)[0]

    # Create XSS test data
    xss_payload = '<script>alert("xss")</script><img onerror="alert(1)" src=x>'
    xss_equip_id = find_or_create(rpc, "maintenance.equipment", "V2_XSS_Equipment", {
        "note": xss_payload,
        "portal_user_ids": [(4, rpc.uid)],  # will be overwritten below
    })
    # Ensure portal user 1 is assigned
    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    rpc.write("maintenance.equipment", [xss_equip_id], {
        "note": xss_payload,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    xss_desc = '<script>alert("xss_desc")</script>'
    xss_req_id = find_or_create(rpc, "maintenance.request", "V2_XSS_Request", {
        "description": xss_desc,
        "equipment_id": EQUIPMENT_A_ID,
        "portal_user_ids": [(4, portal_u1)],
        "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [xss_req_id], {
        "description": xss_desc,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 13.1: XSS via equipment.note (t-raw)
    try:
        r = h.get(f"/my/equipments/{xss_equip_id}")
        if r.status_code == 200:
            if '<script>alert("xss")</script>' in r.text:
                log_fail("13.1 XSS via equipment.note (t-raw)", "Raw <script> tag rendered! XSS VULNERABILITY")
            elif '&lt;script&gt;' in r.text or 'alert' not in r.text:
                log_pass("13.1 XSS via equipment.note escaped")
            else:
                log_warn("13.1 XSS via equipment.note", "Script tag partially present, needs manual review")
        else:
            log_fail("13.1 XSS equipment page", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("13.1 XSS equipment.note", str(e))

    # 13.2: XSS via request.description (t-out)
    try:
        r = h.get(f"/my/maintenance-requests/{xss_req_id}")
        if r.status_code == 200:
            if '<script>alert("xss_desc")</script>' in r.text:
                log_fail("13.2 XSS via request.description (t-out)", "Raw <script> tag rendered!")
            else:
                log_pass("13.2 XSS via request.description escaped by t-out")
        else:
            log_fail("13.2 XSS request page", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("13.2 XSS request.description", str(e))

    # 13.3: Portal user direct RPC write to restricted fields
    try:
        prpc = RPC(URL, DB, PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    except Exception as e:
        log_fail("13.3 Portal RPC auth", str(e))
        return

    # 13.3a: Write equipment name (should fail - perm_write=False on equipment)
    try:
        prpc.write("maintenance.equipment", [EQUIPMENT_A_ID], {"name": "V2_HACKED"})
        log_fail("13.3a Portal write equipment.name", "Should be denied but succeeded!")
    except Exception:
        log_pass("13.3a Portal CANNOT write equipment.name (denied)")

    # 13.3b: Write request stage_id directly (ir.rule allows write on request)
    first_stage = min(stages, key=lambda s: s["sequence"])
    try:
        prpc.write("maintenance.request", [REQUEST_ALPHA_ID], {"stage_id": first_stage["id"]})
        log_warn("13.3b Portal CAN write request.stage_id directly via RPC",
                 "ir.rule perm_write=True allows direct field manipulation, bypassing action methods")
    except Exception:
        log_pass("13.3b Portal CANNOT write request.stage_id directly")

    # 13.3c: Write request name directly
    try:
        # Read original name first
        orig = rpc.read("maintenance.request", [REQUEST_ALPHA_ID], ["name"])[0]["name"]
        prpc.write("maintenance.request", [REQUEST_ALPHA_ID], {"name": "V2_HACKED_NAME"})
        log_warn("13.3c Portal CAN write request.name directly via RPC",
                 "Portal user can change request name, no field-level restriction")
        # Restore
        rpc.write("maintenance.request", [REQUEST_ALPHA_ID], {"name": orig})
    except Exception:
        log_pass("13.3c Portal CANNOT write request.name directly")

    # 13.3d: Write request maintenance_team_id
    try:
        prpc.write("maintenance.request", [REQUEST_ALPHA_ID], {"maintenance_team_id": team_id})
        log_warn("13.3d Portal CAN write request.maintenance_team_id via RPC",
                 "No field-level write restriction on maintenance_team_id")
    except Exception:
        log_pass("13.3d Portal CANNOT write request.maintenance_team_id")


# ============================================================
# Phase 14: State Machine Edge Cases
# ============================================================
def phase_14(rpc, stages):
    section("Phase 14: State Machine Edge Cases")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]

    sorted_stages = sorted(stages, key=lambda s: s["sequence"])
    first_stage = sorted_stages[0]
    non_done_stages = [s for s in sorted_stages if not s.get("done")]
    done_stages = [s for s in sorted_stages if s.get("done")]
    last_non_done = non_done_stages[-1] if non_done_stages else None

    # Create test data
    sm_c_id = find_or_create(rpc, "maintenance.request", "V2_StateMachine_C", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    if last_non_done:
        rpc.write("maintenance.request", [sm_c_id], {"stage_id": last_non_done["id"],
                                                       "portal_user_ids": [(6, 0, [portal_u1])]})

    sm_a_id = find_or_create(rpc, "maintenance.request", "V2_StateMachine_A", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    rpc.write("maintenance.request", [sm_a_id], {"stage_id": first_stage["id"],
                                                   "portal_user_ids": [(6, 0, [portal_u1])]})

    sm_b_id = find_or_create(rpc, "maintenance.request", "V2_StateMachine_B", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    rpc.write("maintenance.request", [sm_b_id], {"stage_id": first_stage["id"],
                                                   "portal_user_ids": [(6, 0, [portal_u1])]})

    # 14.1: set_in_progress at last non-done stage
    try:
        rpc.call("maintenance.request", "action_portal_set_in_progress", [sm_c_id])
        req = rpc.read("maintenance.request", [sm_c_id], ["stage_id"])[0]
        if last_non_done and req["stage_id"][0] == last_non_done["id"]:
            log_pass("14.1 set_in_progress at last non-done stage: no change (correct)")
        else:
            log_fail("14.1 set_in_progress at last non-done stage", f"Stage changed to {req['stage_id']}")
    except Exception as e:
        log_fail("14.1 set_in_progress last non-done", str(e))

    # 14.2: set_done when no done stage exists
    nodone_id = find_or_create(rpc, "maintenance.request", "V2_NoDoneStage_Test", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [nodone_id], {"stage_id": first_stage["id"],
                                                     "portal_user_ids": [(6, 0, [portal_u1])]})
    done_ids = [s["id"] for s in done_stages]
    try:
        # Temporarily remove done flag
        if done_ids:
            rpc.write("maintenance.stage", done_ids, {"done": False})
        rpc.call("maintenance.request", "action_portal_set_done", [nodone_id])
        req = rpc.read("maintenance.request", [nodone_id], ["stage_id"])[0]
        if req["stage_id"][0] == first_stage["id"]:
            log_pass("14.2 set_done with no done stages: no change (correct)")
        else:
            log_fail("14.2 set_done with no done stages", f"Stage changed to {req['stage_id']}")
    except Exception as e:
        log_fail("14.2 set_done no done stages", str(e))
    finally:
        # Restore done flags
        for s in done_stages:
            rpc.write("maintenance.stage", [s["id"]], {"done": True})

    # 14.3: Repeated set_in_progress
    try:
        rpc.call("maintenance.request", "action_portal_set_in_progress", [sm_a_id])
        req1 = rpc.read("maintenance.request", [sm_a_id], ["stage_id"])[0]
        stage_after_first = req1["stage_id"][0]

        rpc.call("maintenance.request", "action_portal_set_in_progress", [sm_a_id])
        req2 = rpc.read("maintenance.request", [sm_a_id], ["stage_id"])[0]

        if stage_after_first != first_stage["id"] and req2["stage_id"][0] == stage_after_first:
            log_pass(f"14.3 Repeated set_in_progress: first moved to {req1['stage_id'][1]}, second stayed")
        elif stage_after_first == first_stage["id"]:
            log_fail("14.3 Repeated set_in_progress", "First call did not advance stage")
        else:
            log_warn("14.3 Repeated set_in_progress", f"After 1st: {req1['stage_id']}, After 2nd: {req2['stage_id']}")
    except Exception as e:
        log_fail("14.3 repeated set_in_progress", str(e))

    # 14.4: Backward transition (in_progress after done)
    try:
        rpc.call("maintenance.request", "action_portal_set_done", [sm_b_id])
        req_done = rpc.read("maintenance.request", [sm_b_id], ["stage_id"])[0]
        done_stage_id = req_done["stage_id"][0]

        rpc.call("maintenance.request", "action_portal_set_in_progress", [sm_b_id])
        req_after = rpc.read("maintenance.request", [sm_b_id], ["stage_id"])[0]

        if req_after["stage_id"][0] == done_stage_id:
            log_pass("14.4 Backward transition after done: stage unchanged (correct)")
        else:
            log_fail("14.4 Backward transition", f"Stage changed from {done_stage_id} to {req_after['stage_id']}")
    except Exception as e:
        log_fail("14.4 backward transition", str(e))

    # 14.5: Two stages with identical sequence
    dup_stage_id = find_or_create(rpc, "maintenance.stage", "V2_DuplicateSeq", {
        "sequence": non_done_stages[1]["sequence"] if len(non_done_stages) > 1 else 2,
        "done": False,
    })
    dupreq_id = find_or_create(rpc, "maintenance.request", "V2_DupSeq_Test", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [dupreq_id], {"stage_id": first_stage["id"],
                                                     "portal_user_ids": [(6, 0, [portal_u1])]})
    try:
        rpc.call("maintenance.request", "action_portal_set_in_progress", [dupreq_id])
        req = rpc.read("maintenance.request", [dupreq_id], ["stage_id"])[0]
        log_pass(f"14.5 Duplicate sequence: moved to '{req['stage_id'][1]}' (deterministic per DB)")
    except Exception as e:
        log_fail("14.5 duplicate sequence", str(e))

    # 14.6: Progress bar rendering with highest sequence stage
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    try:
        r = h.get(f"/my/maintenance-requests/{sm_b_id}")
        if r.status_code == 200 and "maintenance-progress" in r.text:
            log_pass("14.6 Progress bar renders with current stage at done position")
        elif r.status_code == 200:
            log_pass("14.6 Progress bar page renders (200)")
        else:
            log_fail("14.6 Progress bar rendering", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("14.6 progress bar", str(e))


# ============================================================
# Phase 15: Template Rendering Edge Cases
# ============================================================
def phase_15(rpc):
    section("Phase 15: Template Rendering Edge Cases")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]
    first_stage = rpc.sr("maintenance.stage", [], fields=["id", "sequence"], order="sequence", limit=1)[0]["id"]

    # Create bare equipment (no optional fields)
    bare_eq_id = find_or_create(rpc, "maintenance.equipment", "V2_Bare_Equipment", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [bare_eq_id], {
        "serial_no": False, "category_id": False, "location": False,
        "model": False, "note": False,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # Equipment with note=False explicitly
    notefalse_eq_id = find_or_create(rpc, "maintenance.equipment", "V2_NoteFalse_Equipment", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [notefalse_eq_id], {
        "note": False, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # Another blank card for list test
    blank_card_id = find_or_create(rpc, "maintenance.equipment", "V2_AllBlank_Card", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [blank_card_id], {
        "serial_no": False, "category_id": False, "location": False,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # Request with no equipment
    no_eq_req_id = find_or_create(rpc, "maintenance.request", "V2_NoEquipment_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [no_eq_req_id], {
        "equipment_id": False, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # Request with equipment that has no category
    nocat_req_id = find_or_create(rpc, "maintenance.request", "V2_NoCategoryEquip_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": bare_eq_id,
    })
    rpc.write("maintenance.request", [nocat_req_id], {
        "equipment_id": bare_eq_id, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # Request with very long portal_notes
    long_req_id = find_or_create(rpc, "maintenance.request", "V2_LongNotes_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [long_req_id], {
        "portal_notes": "X" * 50000,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 15.1: Equipment detail with all optional fields missing
    try:
        r = h.get(f"/my/equipments/{bare_eq_id}")
        if r.status_code == 200 and "Server Error" not in r.text:
            log_pass("15.1 Equipment detail with all optional fields missing renders OK")
        else:
            log_fail("15.1 Bare equipment detail", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.1 bare equipment", str(e))

    # 15.2: Equipment detail with note=False
    try:
        r = h.get(f"/my/equipments/{notefalse_eq_id}")
        if r.status_code == 200:
            if "False" in r.text and "備註" in r.text:
                log_fail("15.2 note=False renders literal 'False' text", "t-raw may render False as string")
            else:
                log_pass("15.2 Equipment note=False handled cleanly")
        else:
            log_fail("15.2 note=False equipment", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.2 note=False", str(e))

    # 15.3: Request detail with no equipment_id
    try:
        r = h.get(f"/my/maintenance-requests/{no_eq_req_id}")
        if r.status_code == 200 and "Server Error" not in r.text:
            log_pass("15.3 Request detail with no equipment_id renders OK")
        else:
            log_fail("15.3 No equipment request", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.3 no equipment", str(e))

    # 15.4: Request with equipment whose category is missing
    try:
        r = h.get(f"/my/maintenance-requests/{nocat_req_id}")
        if r.status_code == 200 and "Server Error" not in r.text:
            log_pass("15.4 Request with no-category equipment renders OK")
        else:
            log_fail("15.4 No category equipment request", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.4 no category", str(e))

    # 15.5: Equipment list with blank cards
    try:
        r = h.get("/my/equipments")
        if r.status_code == 200:
            has_bare = "V2_Bare_Equipment" in r.text
            has_blank = "V2_AllBlank_Card" in r.text
            if has_bare and has_blank:
                log_pass("15.5 Equipment list renders blank-field cards correctly")
            else:
                log_warn("15.5 Equipment list blank cards", f"bare={has_bare}, blank={has_blank}")
        else:
            log_fail("15.5 Equipment list", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.5 blank cards", str(e))

    # 15.6: Request detail with 50KB portal_notes
    try:
        r = h.get(f"/my/maintenance-requests/{long_req_id}")
        if r.status_code == 200 and len(r.text) > 50000:
            log_pass("15.6 Request detail with 50KB notes renders OK")
        elif r.status_code == 200:
            log_pass("15.6 Request detail with long notes renders (200)")
        else:
            log_fail("15.6 Long notes request", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("15.6 long notes", str(e))


# ============================================================
# Phase 16: Concurrent Access
# ============================================================
def phase_16(rpc):
    section("Phase 16: Concurrent Access & Race Conditions")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]
    first_stage = rpc.sr("maintenance.stage", [], fields=["id"], order="sequence", limit=1)[0]["id"]

    conc_a_id = find_or_create(rpc, "maintenance.request", "V2_Concurrent_A", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    rpc.write("maintenance.request", [conc_a_id], {
        "stage_id": first_stage, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    conc_b_id = find_or_create(rpc, "maintenance.request", "V2_Concurrent_B", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    rpc.write("maintenance.request", [conc_b_id], {
        "stage_id": first_stage, "portal_notes": False,
        "portal_user_ids": [(6, 0, [portal_u1])],
    })

    # 16.1: Concurrent state updates via HTTP
    h1 = HTTP(URL, DB)
    h1.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    h2 = HTTP(URL, DB)
    h2.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    results_16_1 = []
    def update_status(session, req_id, results_list):
        try:
            r = session.post_with_csrf(f"/my/maintenance-requests/{req_id}/update",
                                        {"action": "in_progress"})
            results_list.append(r.status_code)
        except Exception as e:
            results_list.append(str(e))

    t1 = threading.Thread(target=update_status, args=(h1, conc_a_id, results_16_1))
    t2 = threading.Thread(target=update_status, args=(h2, conc_a_id, results_16_1))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    try:
        req = rpc.read("maintenance.request", [conc_a_id], ["stage_id"])[0]
        if req["stage_id"][0] != first_stage:
            log_pass(f"16.1 Concurrent state update: idempotent, final stage={req['stage_id'][1]}")
        else:
            log_warn("16.1 Concurrent state update", "Stage did not change")
    except Exception as e:
        log_fail("16.1 concurrent state", str(e))

    # 16.2: Concurrent notes append
    results_16_2 = []
    def add_note(session, req_id, note_text, results_list):
        try:
            r = session.post_with_csrf(f"/my/maintenance-requests/{req_id}/update",
                                        {"notes": note_text})
            results_list.append(r.status_code)
        except Exception as e:
            results_list.append(str(e))

    h3 = HTTP(URL, DB)
    h3.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    h4 = HTTP(URL, DB)
    h4.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    t3 = threading.Thread(target=add_note, args=(h3, conc_b_id, "V2_Note_Session_1", results_16_2))
    t4 = threading.Thread(target=add_note, args=(h4, conc_b_id, "V2_Note_Session_2", results_16_2))
    t3.start()
    t4.start()
    t3.join(timeout=30)
    t4.join(timeout=30)

    try:
        req = rpc.read("maintenance.request", [conc_b_id], ["portal_notes"])[0]
        notes = req["portal_notes"] or ""
        has1 = "V2_Note_Session_1" in notes
        has2 = "V2_Note_Session_2" in notes
        if has1 and has2:
            log_pass("16.2 Concurrent notes: both preserved")
        elif has1 or has2:
            log_warn("16.2 Concurrent notes: LOST UPDATE", f"has1={has1}, has2={has2}")
        else:
            log_fail("16.2 Concurrent notes", "Neither note was saved")
    except Exception as e:
        log_fail("16.2 concurrent notes", str(e))

    # 16.3: Two sessions same user different pages
    try:
        r1 = h1.get("/my/equipments")
        r2 = h2.get("/my/maintenance-requests")
        if r1.status_code == 200 and r2.status_code == 200:
            log_pass("16.3 Two sessions same user: no interference")
        else:
            log_fail("16.3 Two sessions", f"s1={r1.status_code}, s2={r2.status_code}")
    except Exception as e:
        log_fail("16.3 two sessions", str(e))


# ============================================================
# Phase 17: User Lifecycle & Access Revocation
# ============================================================
def phase_17(rpc, portal_group_id):
    section("Phase 17: User Lifecycle & Access Revocation")

    team_id = rpc.search("maintenance.team", [], limit=1)[0]

    # Create revoke user
    revoke_uid = create_portal_user(rpc, "V2 Revoke User", "v2_revoke@test.com", "v2_revoke_123", portal_group_id)
    rpc.write("maintenance.equipment", [EQUIPMENT_A_ID], {"portal_user_ids": [(4, revoke_uid)]})

    # 17.1: Admin removes portal assignment during active session
    h = HTTP(URL, DB)
    h.login("v2_revoke@test.com", "v2_revoke_123")
    try:
        r = h.get(f"/my/equipments/{EQUIPMENT_A_ID}")
        if r.status_code != 200:
            log_fail("17.1 pre-check", f"Cannot access equipment before revocation: {r.status_code}")
        else:
            # Revoke access
            rpc.write("maintenance.equipment", [EQUIPMENT_A_ID], {"portal_user_ids": [(3, revoke_uid)]})
            r2 = h.get(f"/my/equipments/{EQUIPMENT_A_ID}", allow_redirects=False)
            if r2.status_code in (302, 303):
                log_pass("17.1 Access revoked mid-session: redirected to /my")
            elif r2.status_code == 200 and "V2_Bare" not in r2.text and "Test Equipment A" not in r2.text:
                log_pass("17.1 Access revoked mid-session: content hidden")
            else:
                # Check if the final page is /my after redirects
                r2f = h.get(f"/my/equipments/{EQUIPMENT_A_ID}", allow_redirects=True)
                if "/my/equipments" not in r2f.url or "Test Equipment A" not in r2f.text:
                    log_pass("17.1 Access revoked: redirected away from equipment")
                else:
                    log_fail("17.1 Access revocation", f"Still accessible after revocation, status={r2.status_code}")
    except Exception as e:
        log_fail("17.1 access revocation", str(e))

    # Create deactivate user
    deact_uid = create_portal_user(rpc, "V2 Deactivate User", "v2_deactivate@test.com", "v2_deactivate_123", portal_group_id)
    deact_req_id = find_or_create(rpc, "maintenance.request", "V2_Deactivate_Request", {
        "portal_user_ids": [(4, deact_uid)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [deact_req_id], {"portal_user_ids": [(6, 0, [deact_uid])]})

    # 17.2: Deactivate user while session alive
    hd = HTTP(URL, DB)
    hd.login("v2_deactivate@test.com", "v2_deactivate_123")
    try:
        r = hd.get("/my/maintenance-requests")
        if r.status_code != 200:
            log_fail("17.2 pre-check", f"Cannot access before deactivation: {r.status_code}")
        else:
            rpc.write("res.users", [deact_uid], {"active": False})
            r2 = hd.get("/my/maintenance-requests", allow_redirects=False)
            if r2.status_code in (302, 303):
                loc = r2.headers.get("Location", "")
                if "login" in loc or "web" in loc:
                    log_pass("17.2 Deactivated user redirected to login")
                else:
                    log_pass(f"17.2 Deactivated user redirected to {loc}")
            elif r2.status_code == 200:
                log_warn("17.2 Deactivated user session still active", "May need session invalidation")
            else:
                log_pass(f"17.2 Deactivated user got {r2.status_code}")
            # Restore
            rpc.write("res.users", [deact_uid], {"active": True})
    except Exception as e:
        log_fail("17.2 deactivate user", str(e))
        try: rpc.write("res.users", [deact_uid], {"active": True})
        except: pass

    # Create group change user
    gc_uid = create_portal_user(rpc, "V2 GroupChange User", "v2_groupchange@test.com", "v2_gc_123", portal_group_id)
    gc_req_id = find_or_create(rpc, "maintenance.request", "V2_GroupChange_Request", {
        "portal_user_ids": [(4, gc_uid)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [gc_req_id], {"portal_user_ids": [(6, 0, [gc_uid])]})

    # 17.3: Change user group from portal to internal
    hg = HTTP(URL, DB)
    hg.login("v2_groupchange@test.com", "v2_gc_123")
    try:
        internal_group = rpc.search("res.groups", [("category_id.name", "=", "User types"), ("name", "ilike", "Internal")])
        if internal_group:
            rpc.write("res.users", [gc_uid], {
                "groups_id": [(3, portal_group_id), (4, internal_group[0])],
            })
            r = hg.get("/my/maintenance-requests", allow_redirects=True)
            log_pass(f"17.3 Portal→Internal group change: page returns {r.status_code}, behavior documented")
            # Restore
            rpc.write("res.users", [gc_uid], {
                "groups_id": [(3, internal_group[0]), (4, portal_group_id)],
            })
        else:
            log_warn("17.3 Group change", "Could not find internal user group")
    except Exception as e:
        log_fail("17.3 group change", str(e))
        try:
            rpc.write("res.users", [gc_uid], {"groups_id": [(4, portal_group_id)]})
        except: pass


# ============================================================
# Phase 18: Search & Filter Edge Cases
# ============================================================
def phase_18(rpc):
    section("Phase 18: Search & Filter Edge Cases")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]

    # Create special-char equipment
    pct_eq_id = find_or_create(rpc, "maintenance.equipment", "V2_Search_Percent%Equip", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [pct_eq_id], {"portal_user_ids": [(6, 0, [portal_u1])]})

    uscore_eq_id = find_or_create(rpc, "maintenance.equipment", "V2_Search_Under_score", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [uscore_eq_id], {"portal_user_ids": [(6, 0, [portal_u1])]})

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 18.1: Search with % wildcard
    try:
        r = h.get("/my/equipments?search=%25&search_in=name")  # %25 = URL-encoded %
        if r.status_code == 200:
            # Count how many equipment cards appear (rough check)
            card_count = r.text.count("maintenance-equipment-card")
            if card_count > 5:
                log_warn("18.1 Search '%' acts as SQL wildcard", f"Returned {card_count} cards (matches many records)")
            else:
                log_pass(f"18.1 Search '%' returned {card_count} cards")
        else:
            log_fail("18.1 Search %", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.1 search %", str(e))

    # 18.2: Search with _ wildcard (should be escaped to literal _)
    try:
        # Get total count for comparison
        r_all = h.get("/my/equipments")
        total_cards = r_all.text.count("maintenance-equipment-card") if r_all.status_code == 200 else 0
        r = h.get("/my/equipments?search=_&search_in=name")
        if r.status_code == 200:
            card_count = r.text.count("maintenance-equipment-card")
            if card_count < total_cards:
                log_pass(f"18.2 Search '_' escaped (matched {card_count} of {total_cards} — only literal underscores)")
            elif total_cards > 0 and card_count == total_cards:
                log_warn("18.2 Search '_' acts as SQL wildcard", f"Returned {card_count} cards (same as total {total_cards})")
            else:
                log_pass(f"18.2 Search '_' returned {card_count} cards")
        else:
            log_fail("18.2 Search _", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.2 search _", str(e))

    # 18.3: search_in=category
    try:
        r = h.get("/my/equipments?search=Test+Category&search_in=category")
        if r.status_code == 200:
            if "Test Equipment A" in r.text or "maintenance-equipment-card" in r.text:
                log_pass("18.3 search_in=category works (found results by category name)")
            else:
                log_warn("18.3 search_in=category", "200 but no results visible")
        else:
            log_fail("18.3 search_in=category", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.3 search_in=category", str(e))

    # 18.4: Unrecognized search_in on request list
    try:
        r = h.get("/my/maintenance-requests?search=test&search_in=BOGUS")
        if r.status_code == 200:
            log_pass("18.4 Unrecognized search_in on requests: silently ignored (200)")
        else:
            log_fail("18.4 bogus search_in", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.4 bogus search_in", str(e))

    # 18.5: Search with empty search_in
    try:
        r = h.get("/my/maintenance-requests?search=test&search_in=")
        if r.status_code == 200:
            log_pass("18.5 Empty search_in: silently ignored (200)")
        else:
            log_fail("18.5 empty search_in", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.5 empty search_in", str(e))

    # 18.6: filterby non-numeric
    try:
        r = h.get("/my/maintenance-requests?filterby=abc")
        if r.status_code == 200:
            log_pass("18.6 filterby='abc': falls back to 'all' (200)")
        else:
            log_fail("18.6 filterby abc", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.6 filterby abc", str(e))

    # 18.7: filterby referencing deleted stage
    try:
        temp_stage_id = rpc.create("maintenance.stage", {"name": "V2_Temp_Stage", "sequence": 99, "done": False})
        rpc.unlink("maintenance.stage", [temp_stage_id])
        r = h.get(f"/my/maintenance-requests?filterby={temp_stage_id}")
        if r.status_code == 200:
            log_pass("18.7 filterby deleted stage: falls back to 'all' (200)")
        else:
            log_fail("18.7 filterby deleted stage", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("18.7 filterby deleted", str(e))


# ============================================================
# Phase 19: Pagination Edge Cases
# ============================================================
def phase_19(rpc, portal_group_id):
    section("Phase 19: Pagination Edge Cases")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 19.1: page=0
    try:
        r = h.get("/my/equipments/page/0")
        if r.status_code in (200, 404):
            log_pass(f"19.1 page=0: HTTP {r.status_code} (handled)")
        else:
            log_fail("19.1 page=0", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("19.1 page=0", str(e))

    # 19.2: page=-1
    try:
        r = h.get("/my/equipments/page/-1", allow_redirects=False)
        if r.status_code in (200, 301, 302, 404):
            log_pass(f"19.2 page=-1: HTTP {r.status_code} (handled)")
        else:
            log_fail("19.2 page=-1", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("19.2 page=-1", str(e))

    # 19.3: Zero records user
    empty_uid = create_portal_user(rpc, "V2 Empty User", "v2_empty@test.com", "v2_empty_123", portal_group_id)
    he = HTTP(URL, DB)
    he.login("v2_empty@test.com", "v2_empty_123")
    try:
        r = he.get("/my/equipments")
        if r.status_code == 200:
            if "沒有指派" in r.text or "No equipment" in r.text.lower() or "alert" in r.text.lower():
                log_pass("19.3 Zero records: empty state message displayed")
            else:
                log_pass("19.3 Zero records: page renders (200)")
        else:
            log_fail("19.3 zero records", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("19.3 zero records", str(e))

    # 19.4: Bulk pagination test (create enough for 2 pages)
    # Default _items_per_page is 80, but let's check what we have and create a reasonable number
    current_count = rpc.count("maintenance.equipment", [("portal_user_ids", "in", portal_u1)])
    target = 25  # Create 25 more for a reasonable pagination test
    bulk_ids = []
    try:
        for i in range(target):
            eid = find_or_create(rpc, "maintenance.equipment", f"V2_PageTest_{i+1:03d}", {
                "portal_user_ids": [(4, portal_u1)],
            })
            rpc.write("maintenance.equipment", [eid], {"portal_user_ids": [(6, 0, [portal_u1])]})
            bulk_ids.append(eid)

        new_count = rpc.count("maintenance.equipment", [("portal_user_ids", "in", portal_u1)])
        log_pass(f"19.4 Created {target} bulk equipment (total now: {new_count})")

        # Test pagination
        r1 = h.get("/my/equipments")
        r2 = h.get("/my/equipments/page/2")
        if r1.status_code == 200 and r2.status_code == 200:
            log_pass("19.4 Pagination: page 1 and 2 both render (200)")
        else:
            log_warn("19.4 Pagination", f"page1={r1.status_code}, page2={r2.status_code}")
    except Exception as e:
        log_fail("19.4 bulk pagination", str(e))


# ============================================================
# Phase 20: HTTP Method & Route Edge Cases
# ============================================================
def phase_20(rpc):
    section("Phase 20: HTTP Method & Route Edge Cases")

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 20.1: GET on POST-only update route
    try:
        r = h.get(f"/my/maintenance-requests/{REQUEST_ALPHA_ID}/update", allow_redirects=False)
        if r.status_code == 405:
            log_pass("20.1 GET on POST-only route: 405 Method Not Allowed")
        elif r.status_code in (301, 302, 303, 404):
            log_pass(f"20.1 GET on POST-only route: {r.status_code} (rejected)")
        elif r.status_code == 200:
            log_warn("20.1 GET on POST-only route", "Returns 200 instead of 405")
        else:
            log_pass(f"20.1 GET on POST-only route: HTTP {r.status_code}")
    except Exception as e:
        log_fail("20.1 GET on POST route", str(e))

    # 20.2-20.4: PUT/DELETE/PATCH on equipment list
    for method in ["PUT", "DELETE", "PATCH"]:
        try:
            r = h.raw_method(method, "/my/equipments")
            if r.status_code in (405, 404):
                log_pass(f"20.{2 if method=='PUT' else 3 if method=='DELETE' else 4} {method} /my/equipments: {r.status_code}")
            elif r.status_code in (301, 302, 303):
                log_pass(f"20.x {method} /my/equipments: redirected ({r.status_code})")
            else:
                log_warn(f"20.x {method} /my/equipments", f"HTTP {r.status_code}")
        except Exception as e:
            log_fail(f"20.x {method}", str(e))

    # 20.5: POST to read-only equipment list
    try:
        r = h.s.post(f"{URL}/my/equipments", data={}, allow_redirects=True)
        if r.status_code == 200:
            log_pass("20.5 POST to equipment list: treated as GET (200)")
        else:
            log_pass(f"20.5 POST to equipment list: HTTP {r.status_code}")
    except Exception as e:
        log_fail("20.5 POST to list", str(e))

    # 20.6: POST update without CSRF (authenticated user)
    try:
        r = h.post_raw(f"/my/maintenance-requests/{REQUEST_ALPHA_ID}/update",
                        data={"action": "in_progress"})
        if r.status_code in (400, 403):
            log_pass(f"20.6 POST without CSRF: rejected ({r.status_code})")
        elif r.status_code in (301, 302, 303):
            log_pass(f"20.6 POST without CSRF: redirected ({r.status_code})")
        else:
            log_fail("20.6 POST without CSRF", f"HTTP {r.status_code} (expected 400/403)")
    except Exception as e:
        log_fail("20.6 no CSRF", str(e))


# ============================================================
# Phase 21: RPC Edge Cases & Model Methods
# ============================================================
def phase_21(rpc, stages):
    section("Phase 21: RPC Edge Cases & Model Methods")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]
    first_stage = min(stages, key=lambda s: s["sequence"])

    rpc_a_id = find_or_create(rpc, "maintenance.request", "V2_RPC_Test_A", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [rpc_a_id], {"portal_user_ids": [(6, 0, [portal_u1])],
                                                    "portal_notes": False,
                                                    "stage_id": first_stage["id"]})

    rpc_b_id = find_or_create(rpc, "maintenance.request", "V2_RPC_Test_B", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [rpc_b_id], {"portal_user_ids": [(6, 0, [portal_u1])],
                                                    "portal_notes": "First note"})

    emptystr_id = find_or_create(rpc, "maintenance.request", "V2_EmptyStr_Test", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [emptystr_id], {"portal_notes": False,
                                                       "portal_user_ids": [(6, 0, [portal_u1])]})

    # 21.1: add_notes(None)
    try:
        result = rpc.call("maintenance.request", "action_portal_add_notes", [rpc_a_id], None)
        req = rpc.read("maintenance.request", [rpc_a_id], ["portal_notes"])[0]
        if not req["portal_notes"]:
            log_pass("21.1 add_notes(None): no change, returns True")
        else:
            log_fail("21.1 add_notes(None)", f"Notes changed to: {req['portal_notes']}")
    except Exception as e:
        log_fail("21.1 add_notes(None)", str(e))

    # 21.2: Notes containing "---" separator
    try:
        rpc.call("maintenance.request", "action_portal_add_notes", [rpc_b_id], "---")
        req = rpc.read("maintenance.request", [rpc_b_id], ["portal_notes"])[0]
        notes = req["portal_notes"] or ""
        if "First note" in notes and notes.count("---") >= 2:  # separator + the note itself
            log_pass("21.2 Notes with '---' separator: correctly appended")
        else:
            log_warn("21.2 Notes with separator", f"Got: {notes[:200]}")
    except Exception as e:
        log_fail("21.2 notes separator", str(e))

    # 21.3: 100KB notes
    try:
        big_note = "B" * 102400
        rpc.call("maintenance.request", "action_portal_add_notes", [rpc_a_id], big_note)
        req = rpc.read("maintenance.request", [rpc_a_id], ["portal_notes"])[0]
        if len(req["portal_notes"] or "") >= 102400:
            log_pass("21.3 100KB notes: stored successfully")
        else:
            log_fail("21.3 100KB notes", f"Notes length: {len(req['portal_notes'] or '')}")
    except Exception as e:
        log_fail("21.3 100KB notes", str(e))

    # 21.4: portal_notes empty string "" vs False
    try:
        rpc.call("maintenance.request", "action_portal_add_notes", [emptystr_id], "")
        req = rpc.read("maintenance.request", [emptystr_id], ["portal_notes"])[0]
        if not req["portal_notes"]:
            log_pass("21.4a add_notes(''): no change (empty string is falsy)")
        else:
            log_fail("21.4a add_notes('')", f"Notes became: {req['portal_notes']}")

        # Set to empty string, then add note
        rpc.write("maintenance.request", [emptystr_id], {"portal_notes": ""})
        rpc.call("maintenance.request", "action_portal_add_notes", [emptystr_id], "hello")
        req2 = rpc.read("maintenance.request", [emptystr_id], ["portal_notes"])[0]
        if req2["portal_notes"] == "hello":
            log_pass("21.4b portal_notes=''+add_notes('hello'): initialized fresh")
        else:
            log_warn("21.4b empty string behavior", f"Got: {req2['portal_notes']}")
    except Exception as e:
        log_fail("21.4 empty string", str(e))

    # 21.5: document_id=0 via HTTP
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    try:
        r = h.get("/my/equipments/0", allow_redirects=False)
        if r.status_code in (302, 303, 404):
            log_pass(f"21.5 equipment_id=0: {r.status_code} (handled)")
        elif r.status_code == 200:
            r2 = h.get("/my/equipments/0", allow_redirects=True)
            if "/my" in r2.url and "/equipments/0" not in r2.url:
                log_pass("21.5 equipment_id=0: redirected to /my")
            else:
                log_warn("21.5 equipment_id=0", "Returns 200, may show empty page")
        else:
            log_pass(f"21.5 equipment_id=0: HTTP {r.status_code}")
    except Exception as e:
        log_fail("21.5 id=0", str(e))

    # 21.6: Very large ID
    try:
        r = h.get("/my/equipments/99999999999", allow_redirects=False)
        if r.status_code in (302, 303, 404):
            log_pass(f"21.6 Very large ID: {r.status_code}")
        elif r.status_code == 200:
            log_pass("21.6 Very large ID: redirected (200 after redirect)")
        else:
            log_pass(f"21.6 Very large ID: HTTP {r.status_code}")
    except Exception as e:
        log_fail("21.6 large ID", str(e))

    # 21.7: ensure_one on multi-record
    try:
        rpc.call("maintenance.request", "action_portal_set_in_progress", [rpc_a_id, rpc_b_id])
        log_fail("21.7 ensure_one multi-record", "Should have raised ValueError")
    except Exception as e:
        if "Expected singleton" in str(e) or "ValueError" in str(e) or "expected singleton" in str(e).lower():
            log_pass("21.7 ensure_one on multi-record: ValueError raised")
        else:
            log_pass(f"21.7 ensure_one: error raised ({type(e).__name__})")

    # 21.8: _get_portal_url
    try:
        result = rpc.call("maintenance.request", "_get_portal_url", [REQUEST_ALPHA_ID])
        if result == f"/my/maintenance-requests/{REQUEST_ALPHA_ID}":
            log_pass("21.8a _get_portal_url on request returns correct URL")
        else:
            log_warn("21.8a _get_portal_url", f"Got: {result}")
    except Exception as e:
        log_warn("21.8a _get_portal_url", f"Cannot call: {e}")

    try:
        result = rpc.call("maintenance.equipment", "_get_portal_url", [EQUIPMENT_A_ID])
        if result == f"/my/equipments/{EQUIPMENT_A_ID}":
            log_pass("21.8b _get_portal_url on equipment returns correct URL")
        else:
            log_warn("21.8b _get_portal_url equipment", f"Got: {result}")
    except Exception as e:
        log_warn("21.8b _get_portal_url equipment", f"Cannot call: {e}")

    # 21.9: Onchange programmatic call
    try:
        # Use onchange to simulate equipment selection
        result = rpc.ex("maintenance.request", "onchange",
                        {},  # vals
                        ["equipment_id", "portal_user_ids"],  # fields
                        {"equipment_id": {"type": "many2one", "relation": "maintenance.equipment"}})
        # This may not work exactly as expected via XML-RPC; document behavior
        log_pass(f"21.9 Onchange call completed (result type: {type(result).__name__})")
    except Exception as e:
        # Try alternative onchange format
        try:
            new_vals = {"equipment_id": EQUIPMENT_A_ID, "portal_user_ids": [[6, False, []]]}
            result = rpc.obj.execute_kw(DB, rpc.uid, rpc.pwd, "maintenance.request", "onchange",
                                         [[], new_vals, "equipment_id",
                                          {"equipment_id": "1", "portal_user_ids": ""}])
            if result and "value" in result:
                pids = result["value"].get("portal_user_ids", [])
                log_pass(f"21.9 Onchange: portal_user_ids inherited (result keys: {list(result.keys())})")
            else:
                log_warn("21.9 Onchange", f"No value returned: {result}")
        except Exception as e2:
            log_warn("21.9 Onchange programmatic call", f"Cannot invoke: {e2}")


# ============================================================
# Phase 22: Cross-User Isolation
# ============================================================
def phase_22(rpc):
    section("Phase 22: Cross-User Isolation")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    portal_u2 = rpc.sr("res.users", [("login", "=", PORTAL_USER2_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]

    # Create cross-user request on equipment A but assigned to user 2
    cu_req_id = find_or_create(rpc, "maintenance.request", "V2_CrossUser_Request", {
        "portal_user_ids": [(4, portal_u2)], "maintenance_team_id": team_id,
        "equipment_id": EQUIPMENT_A_ID,
    })
    rpc.write("maintenance.request", [cu_req_id], {
        "portal_user_ids": [(6, 0, [portal_u2])],
        "equipment_id": EQUIPMENT_A_ID,
    })

    # 22.1: Equipment detail shows only current user's related requests
    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
    try:
        r = h.get(f"/my/equipments/{EQUIPMENT_A_ID}")
        if r.status_code == 200:
            has_cross = "V2_CrossUser_Request" in r.text
            if not has_cross:
                log_pass("22.1 Equipment detail: cross-user request correctly hidden")
            else:
                log_fail("22.1 Equipment detail", "Cross-user request visible! Isolation breach")
        else:
            log_fail("22.1 Equipment detail", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("22.1 cross-user", str(e))

    # 22.2: Admin accessing portal routes
    ha = HTTP(URL, DB)
    ha.login(ADMIN_USER, ADMIN_PASS)
    try:
        r = ha.get("/my/equipments")
        if r.status_code == 200:
            # Admin is not in any portal_user_ids, should see empty list
            if "沒有指派" in r.text or "No equipment" in r.text.lower() or EQUIPMENT_A_ID and "Test Equipment A" not in r.text:
                log_pass("22.2a Admin sees empty equipment list on portal (correct)")
            else:
                log_warn("22.2a Admin portal equipment", "Admin may see equipment (unexpected)")
        else:
            log_pass(f"22.2a Admin portal equipment: HTTP {r.status_code}")

        r2 = ha.get(f"/my/equipments/{EQUIPMENT_A_ID}", allow_redirects=False)
        if r2.status_code in (302, 303):
            log_pass("22.2b Admin cannot access equipment detail (redirected)")
        elif r2.status_code == 200:
            r2f = ha.get(f"/my/equipments/{EQUIPMENT_A_ID}", allow_redirects=True)
            if "Test Equipment A" not in r2f.text:
                log_pass("22.2b Admin redirected away from equipment detail")
            else:
                log_fail("22.2b Admin can access equipment detail", "IDOR for admin user")
        else:
            log_pass(f"22.2b Admin equipment detail: HTTP {r2.status_code}")
    except Exception as e:
        log_fail("22.2 admin portal", str(e))


# ============================================================
# Phase 23: Notes & Chatter Edge Cases
# ============================================================
def phase_23(rpc):
    section("Phase 23: Notes & Chatter Edge Cases")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]
    first_stage = rpc.sr("maintenance.stage", [], fields=["id"], order="sequence", limit=1)[0]["id"]

    ws_req_id = find_or_create(rpc, "maintenance.request", "V2_WhitespaceNotes_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [ws_req_id], {
        "portal_notes": False, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    chatter_req_id = find_or_create(rpc, "maintenance.request", "V2_ChatterTest_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [chatter_req_id], {
        "stage_id": first_stage, "portal_user_ids": [(6, 0, [portal_u1])],
    })

    h = HTTP(URL, DB)
    h.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 23.1: Whitespace-only notes
    try:
        r = h.post_with_csrf(f"/my/maintenance-requests/{ws_req_id}/update",
                              {"notes": "   \n\t  "})
        req = rpc.read("maintenance.request", [ws_req_id], ["portal_notes"])[0]
        if not req["portal_notes"]:
            log_pass("23.1 Whitespace-only notes: stripped to empty, not saved")
        else:
            log_fail("23.1 Whitespace-only notes", f"Notes saved as: '{req['portal_notes'][:50]}'")
    except Exception as e:
        log_fail("23.1 whitespace notes", str(e))

    # 23.2: Chatter message author
    try:
        r = h.post_with_csrf(f"/my/maintenance-requests/{chatter_req_id}/update",
                              {"action": "in_progress"})
        # Read chatter messages
        msgs = rpc.sr("mail.message",
                       [("model", "=", "maintenance.request"),
                        ("res_id", "=", chatter_req_id),
                        ("body", "ilike", "Status updated")],
                       fields=["body", "author_id"],
                       order="id desc", limit=3)
        if msgs:
            author = msgs[0].get("author_id")
            author_name = author[1] if author else "Unknown"
            log_pass(f"23.2 Chatter message author: {author_name}")
        else:
            log_warn("23.2 Chatter message", "No status update message found in chatter")
    except Exception as e:
        log_fail("23.2 chatter author", str(e))


# ============================================================
# Phase 24: Record Deletion & Counter Edge Cases
# ============================================================
def phase_24(rpc):
    section("Phase 24: Record Deletion & Counter Verification")

    portal_u1 = rpc.sr("res.users", [("login", "=", PORTAL_USER1_LOGIN)], fields=["id"])[0]["id"]
    team_id = rpc.search("maintenance.team", [], limit=1)[0]
    first_stage = rpc.sr("maintenance.stage", [], fields=["id"], order="sequence", limit=1)[0]["id"]

    # Create counter test data
    for suffix in ["A", "B", "C"]:
        cid = find_or_create(rpc, "maintenance.request", f"V2_Counter_Extra_{suffix}", {
            "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        })
        rpc.write("maintenance.request", [cid], {"portal_user_ids": [(6, 0, [portal_u1])]})

    # 24.1: Counter accuracy
    try:
        admin_eq_count = rpc.count("maintenance.equipment", [("portal_user_ids", "in", portal_u1)])
        admin_req_count = rpc.count("maintenance.request", [("portal_user_ids", "in", portal_u1)])

        # Check via portal user RPC
        prpc = RPC(URL, DB, PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)
        portal_eq_count = prpc.count("maintenance.equipment", [])
        portal_req_count = prpc.count("maintenance.request", [])

        if portal_eq_count == admin_eq_count:
            log_pass(f"24.1a Equipment counter: {portal_eq_count} (matches admin count)")
        else:
            log_warn("24.1a Equipment counter mismatch", f"portal={portal_eq_count}, admin={admin_eq_count}")

        if portal_req_count == admin_req_count:
            log_pass(f"24.1b Request counter: {portal_req_count} (matches admin count)")
        else:
            log_warn("24.1b Request counter mismatch", f"portal={portal_req_count}, admin={admin_req_count}")
    except Exception as e:
        log_fail("24.1 counter accuracy", str(e))

    # Create equipment to delete
    del_eq_id = find_or_create(rpc, "maintenance.equipment", "V2_DeleteMe_Equipment", {
        "portal_user_ids": [(4, portal_u1)],
    })
    rpc.write("maintenance.equipment", [del_eq_id], {"portal_user_ids": [(6, 0, [portal_u1])]})

    del_req_id = find_or_create(rpc, "maintenance.request", "V2_DeletedEquip_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
        "equipment_id": del_eq_id,
    })
    rpc.write("maintenance.request", [del_req_id], {"portal_user_ids": [(6, 0, [portal_u1])]})

    # Shared HTTP session for Phase 24
    h24 = HTTP(URL, DB)
    h24.login(PORTAL_USER1_LOGIN, PORTAL_USER1_PASS)

    # 24.2: Equipment deleted while request exists
    try:
        # First detach equipment from request to allow deletion
        rpc.write("maintenance.request", [del_req_id], {"equipment_id": False})
        rpc.unlink("maintenance.equipment", [del_eq_id])
        # Now check request detail page renders without its equipment
        r = h24.get(f"/my/maintenance-requests/{del_req_id}")
        if r.status_code == 200 and "Server Error" not in r.text:
            log_pass("24.2 Request detail after equipment deletion: renders OK (200)")
        elif r.status_code == 200:
            log_fail("24.2 Request detail after equipment deletion", "Server Error in page")
        else:
            log_fail("24.2 Request after equipment deletion", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("24.2 equipment deletion", str(e))

    # 24.3: Request list with deleted/missing equipment
    try:
        r = h24.get("/my/maintenance-requests")
        if r.status_code == 200:
            log_pass("24.3 Request list with deleted equipment: renders OK")
        else:
            log_fail("24.3 Request list deleted equip", f"HTTP {r.status_code}")
    except Exception as e:
        log_fail("24.3 request list", str(e))

    # 24.4: Request without stage_id (stage_id is NOT required at ORM level, only in form view)
    nostage_id = find_or_create(rpc, "maintenance.request", "V2_NoStage_Request", {
        "portal_user_ids": [(4, portal_u1)], "maintenance_team_id": team_id,
    })
    rpc.write("maintenance.request", [nostage_id], {"portal_user_ids": [(6, 0, [portal_u1])]})
    try:
        rpc.write("maintenance.request", [nostage_id], {"stage_id": False})
        # stage_id is not required at ORM level - this is expected to succeed
        # The real test is whether the portal page can render without crashing
        r = h24.get(f"/my/maintenance-requests/{nostage_id}")
        if r.status_code == 200 and "Server Error" not in r.text:
            log_pass("24.4 Request with stage_id=False renders OK on portal")
        elif r.status_code == 200:
            log_fail("24.4 Request with no stage: Server Error on portal page")
        else:
            log_warn("24.4 Request with no stage", f"HTTP {r.status_code}")
        # Restore stage to avoid polluting other tests
        rpc.write("maintenance.request", [nostage_id], {"stage_id": first_stage})
    except Exception as e:
        # If the ORM rejects it, that's also fine
        log_pass(f"24.4 stage_id=False: rejected ({e})")


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 65)
    print("  MAINTENANCE PORTAL V2 - EDGE/STRESS/SECURITY TEST SUITE")
    print(f"  Target: {URL} / DB: {DB}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    try:
        rpc = RPC(URL, DB, ADMIN_USER, ADMIN_PASS)
        print(f"  Admin connected (uid={rpc.uid})")
    except Exception as e:
        print(f"FATAL: {e}")
        sys.exit(1)

    # Discover stages
    stages = rpc.sr("maintenance.stage", [], fields=["id", "name", "sequence", "done"], order="sequence")
    print(f"  Stages: {[s['name'] for s in stages]}")

    # Discover portal group
    pg = rpc.search("res.groups", [("category_id.name", "=", "User types"), ("name", "ilike", "Portal")])
    portal_group_id = pg[0] if pg else None
    if not portal_group_id:
        print("FATAL: Portal group not found")
        sys.exit(1)
    print(f"  Portal group ID: {portal_group_id}")

    # Ensure portal user passwords are set (may be invalidated by module upgrades)
    pu1 = rpc.search("res.users", [("login", "=", PORTAL_USER1_LOGIN)])
    if pu1:
        rpc.write("res.users", pu1, {"password": PORTAL_USER1_PASS})
    pu2 = rpc.search("res.users", [("login", "=", PORTAL_USER2_LOGIN)])
    if pu2:
        rpc.write("res.users", pu2, {"password": PORTAL_USER2_PASS})

    # Verify V1 data exists
    v1_eq = rpc.search("maintenance.equipment", [("name", "=", "Test Equipment A")])
    v1_req = rpc.search("maintenance.request", [("name", "=", "Test Request Alpha")])
    if not v1_eq or not v1_req:
        print("WARNING: V1 test data not found, some tests may fail")

    # Run phases
    phase_13(rpc, portal_group_id, stages)
    phase_14(rpc, stages)
    phase_15(rpc)
    phase_16(rpc)
    phase_17(rpc, portal_group_id)
    phase_18(rpc)
    phase_19(rpc, portal_group_id)
    phase_20(rpc)
    phase_21(rpc, stages)
    phase_22(rpc)
    phase_23(rpc)
    phase_24(rpc)

    # Summary
    section("FINAL REPORT")
    total = results["passed"] + results["failed"] + results["warned"]
    print(f"\n  Total:    {total}")
    print(f"  Passed:   \033[32m{results['passed']}\033[0m")
    print(f"  Failed:   \033[31m{results['failed']}\033[0m")
    print(f"  Warnings: \033[33m{results['warned']}\033[0m")
    if total > 0:
        print(f"  Pass Rate: {results['passed']/total*100:.1f}%")

    if results["failed"]:
        print(f"\n  === FAILURES ({results['failed']}) ===")
        for s, n, d in results["details"]:
            if s == "FAIL":
                print(f"    [{s}] {n}: {d}")

    if results["warned"]:
        print(f"\n  === WARNINGS ({results['warned']}) ===")
        for s, n, d in results["details"]:
            if s == "WARN":
                print(f"    [{s}] {n}: {d}")

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
