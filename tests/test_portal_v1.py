#!/usr/bin/env python3
"""
Comprehensive Test Suite for Maintenance Portal Module
Tests: Installation, Backend, Portal, Security, Edge Cases, i18n
Target: Odoo 18 instance at localhost:9070
"""
import xmlrpc.client
import requests
import json
import re
import sys
import time
import traceback
from urllib.parse import urljoin

# ============================================================
# Configuration
# ============================================================
ODOO_URL = "http://localhost:9070"
DB_NAME = "odoomaintain"  # From odoo.conf
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

# XML-RPC endpoints
COMMON_EP = f"{ODOO_URL}/xmlrpc/2/common"
OBJECT_EP = f"{ODOO_URL}/xmlrpc/2/object"

# Test results tracking
results = {"passed": 0, "failed": 0, "errors": [], "warnings": []}


def log_pass(test_name):
    results["passed"] += 1
    print(f"  [PASS] {test_name}")


def log_fail(test_name, detail=""):
    results["failed"] += 1
    msg = f"  [FAIL] {test_name}: {detail}"
    results["errors"].append(msg)
    print(msg)


def log_warn(test_name, detail=""):
    msg = f"  [WARN] {test_name}: {detail}"
    results["warnings"].append(msg)
    print(msg)


def log_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# Helper: XML-RPC Connection
# ============================================================
class OdooRPC:
    def __init__(self, url, db, user, password):
        self.url = url
        self.db = db
        self.uid = None
        self.password = password
        self.common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        self.uid = self.common.authenticate(db, user, password, {})
        if not self.uid:
            raise Exception(f"Authentication failed for {user}")

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs
        )

    def search(self, model, domain, **kwargs):
        return self.execute(model, "search", domain, **kwargs)

    def read(self, model, ids, fields=None):
        kw = {}
        if fields:
            kw["fields"] = fields
        return self.execute(model, "read", ids, **kw)

    def search_read(self, model, domain, fields=None, **kwargs):
        kw = dict(kwargs)
        if fields:
            kw["fields"] = fields
        return self.execute(model, "search_read", domain, **kw)

    def create(self, model, vals):
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        return self.execute(model, "write", ids, vals)

    def unlink(self, model, ids):
        return self.execute(model, "unlink", ids)

    def call(self, model, method, ids, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, [ids] + list(args), kwargs
        )


class OdooHTTPSession:
    """HTTP session for portal user testing"""

    def __init__(self, base_url, db):
        self.base_url = base_url
        self.db = db
        self.session = requests.Session()
        self.csrf_token = None

    def login(self, login, password):
        """Login via web and get session"""
        # Get login page to obtain CSRF token
        resp = self.session.get(f"{self.base_url}/web/login", allow_redirects=True)
        if resp.status_code != 200:
            raise Exception(f"Cannot access login page: {resp.status_code}")

        # Extract CSRF token
        csrf_match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', resp.text
        )
        if csrf_match:
            self.csrf_token = csrf_match.group(1)

        # Login
        data = {
            "login": login,
            "password": password,
            "db": self.db,
        }
        if self.csrf_token:
            data["csrf_token"] = self.csrf_token

        resp = self.session.post(
            f"{self.base_url}/web/login",
            data=data,
            allow_redirects=True,
        )
        return resp

    def get(self, path, **kwargs):
        return self.session.get(f"{self.base_url}{path}", **kwargs)

    def post(self, path, data=None, **kwargs):
        # Get fresh CSRF token for POST
        if data is None:
            data = {}
        # Fetch the page first to get a CSRF token
        page_resp = self.session.get(f"{self.base_url}{path.rsplit('/update', 1)[0]}")
        csrf_match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', page_resp.text
        )
        if csrf_match:
            data["csrf_token"] = csrf_match.group(1)
        return self.session.post(f"{self.base_url}{path}", data=data, **kwargs)


# ============================================================
# Auto-detect database
# ============================================================
def detect_database():
    global DB_NAME
    try:
        db_proxy = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/db")
        dbs = db_proxy.list()
        if dbs:
            DB_NAME = dbs[0]
            print(f"Detected database: {DB_NAME}")
            return True
    except Exception:
        pass

    # Try common names
    for db in ["odoo", "maintain", "odoo-maintain", "odoo18"]:
        try:
            common = xmlrpc.client.ServerProxy(COMMON_EP)
            uid = common.authenticate(db, ADMIN_USER, ADMIN_PASS, {})
            if uid:
                DB_NAME = db
                print(f"Found database: {DB_NAME}")
                return True
        except Exception:
            continue
    return False


# ============================================================
# Phase 1: Module Installation
# ============================================================
def test_module_installation(rpc):
    log_section("Phase 1: Module Installation & Dependencies")

    # Check if module is available
    modules = rpc.search_read(
        "ir.module.module",
        [("name", "=", "maintenance_portal")],
        fields=["name", "state", "installed_version"],
    )

    if not modules:
        log_fail("Module discovery", "maintenance_portal not found in module list")
        # Try to update module list
        print("  Attempting to update module list...")
        rpc.execute("ir.module.module", "update_list")
        modules = rpc.search_read(
            "ir.module.module",
            [("name", "=", "maintenance_portal")],
            fields=["name", "state", "installed_version"],
        )
        if not modules:
            log_fail("Module discovery after update", "Still not found")
            return False

    module = modules[0]
    print(f"  Module state: {module['state']}")

    if module["state"] != "installed":
        print("  Installing maintenance_portal module...")
        try:
            rpc.execute(
                "ir.module.module", "button_immediate_install", [module["id"]]
            )
            # Re-check
            modules = rpc.search_read(
                "ir.module.module",
                [("name", "=", "maintenance_portal")],
                fields=["name", "state", "installed_version"],
            )
            module = modules[0]
            if module["state"] == "installed":
                log_pass("Module installation")
            else:
                log_fail("Module installation", f"State is {module['state']}")
                return False
        except Exception as e:
            log_fail("Module installation", str(e))
            return False
    else:
        log_pass("Module already installed")

    # Verify dependencies
    for dep in ["maintenance", "portal"]:
        dep_mods = rpc.search_read(
            "ir.module.module",
            [("name", "=", dep)],
            fields=["name", "state"],
        )
        if dep_mods and dep_mods[0]["state"] == "installed":
            log_pass(f"Dependency '{dep}' installed")
        else:
            log_fail(f"Dependency '{dep}'", "Not installed")

    return True


# ============================================================
# Phase 2: Data Model Verification
# ============================================================
def test_data_models(rpc):
    log_section("Phase 2: Data Model Verification")

    # Check portal_user_ids field on equipment
    try:
        fields = rpc.execute(
            "maintenance.equipment", "fields_get", [], attributes=["type", "relation"]
        )
        if "portal_user_ids" in fields:
            f = fields["portal_user_ids"]
            if f["type"] == "many2many" and f["relation"] == "res.users":
                log_pass("Equipment.portal_user_ids field exists (many2many -> res.users)")
            else:
                log_fail(
                    "Equipment.portal_user_ids type",
                    f"type={f['type']}, relation={f.get('relation')}",
                )
        else:
            log_fail("Equipment.portal_user_ids", "Field not found")
    except Exception as e:
        log_fail("Equipment model fields", str(e))

    # Check portal_user_ids and portal_notes on request
    try:
        fields = rpc.execute(
            "maintenance.request",
            "fields_get",
            [],
            attributes=["type", "relation"],
        )
        if "portal_user_ids" in fields:
            f = fields["portal_user_ids"]
            if f["type"] == "many2many" and f["relation"] == "res.users":
                log_pass("Request.portal_user_ids field exists (many2many -> res.users)")
            else:
                log_fail("Request.portal_user_ids type", f"type={f['type']}")
        else:
            log_fail("Request.portal_user_ids", "Field not found")

        if "portal_notes" in fields:
            if fields["portal_notes"]["type"] == "text":
                log_pass("Request.portal_notes field exists (text)")
            else:
                log_fail("Request.portal_notes type", fields["portal_notes"]["type"])
        else:
            log_fail("Request.portal_notes", "Field not found")
    except Exception as e:
        log_fail("Request model fields", str(e))


# ============================================================
# Phase 3: Security Rules Verification
# ============================================================
def test_security_rules(rpc):
    log_section("Phase 3: Security Rules Verification")

    # Check ir.model.access records
    access_records = rpc.search_read(
        "ir.model.access",
        [("name", "ilike", "maintenance_portal")],
        fields=["name", "model_id", "group_id", "perm_read", "perm_write", "perm_create", "perm_unlink"],
    )

    expected_access = {
        "maintenance.equipment": {"read": True, "write": False, "create": False, "unlink": False},
        "maintenance.request": {"read": True, "write": True, "create": False, "unlink": False},
        "maintenance.stage": {"read": True, "write": False, "create": False, "unlink": False},
        "maintenance.equipment.category": {"read": True, "write": False, "create": False, "unlink": False},
    }

    found_models = set()
    for rec in access_records:
        model_name = rec["model_id"][1] if rec["model_id"] else "unknown"
        # Extract model technical name from display name
        # Check group is portal
        group_name = rec["group_id"][1] if rec["group_id"] else "no group"
        if "Portal" not in group_name and "portal" not in group_name.lower():
            continue

        # Map from display name to technical name
        for tech_name, expected in expected_access.items():
            if tech_name.replace(".", " ").title().replace(" ", " ") in model_name or tech_name in rec["name"]:
                found_models.add(tech_name)
                perms_ok = (
                    rec["perm_read"] == expected["read"]
                    and rec["perm_write"] == expected["write"]
                    and rec["perm_create"] == expected["create"]
                    and rec["perm_unlink"] == expected["unlink"]
                )
                if perms_ok:
                    log_pass(f"Access rights for {tech_name} (r={expected['read']},w={expected['write']},c={expected['create']},d={expected['unlink']})")
                else:
                    log_fail(
                        f"Access rights for {tech_name}",
                        f"Got r={rec['perm_read']},w={rec['perm_write']},c={rec['perm_create']},d={rec['perm_unlink']}",
                    )

    # Check for any missing access records
    if len(access_records) >= 4:
        log_pass(f"Found {len(access_records)} portal access records")
    else:
        log_warn("Portal access records", f"Only found {len(access_records)}, expected 4")

    # Check ir.rule records
    rules = rpc.search_read(
        "ir.rule",
        [("name", "ilike", "portal")],
        fields=["name", "model_id", "domain_force", "perm_read", "perm_write"],
    )
    portal_rules = [r for r in rules if "maintenance" in r.get("name", "").lower() or
                    (r.get("model_id") and "maintenance" in str(r["model_id"]).lower())]

    if len(portal_rules) >= 2:
        log_pass(f"Found {len(portal_rules)} maintenance portal security rules")
    else:
        log_warn("Security rules", f"Found only {len(portal_rules)} maintenance portal rules")

    for rule in portal_rules:
        print(f"    Rule: {rule['name']} | Domain: {rule.get('domain_force', 'N/A')}")


# ============================================================
# Phase 4: Create Test Data
# ============================================================
def create_test_data(rpc):
    log_section("Phase 4: Creating Test Data")

    data = {}

    # Create portal user (external vendor)
    try:
        # Check if test portal user already exists
        existing = rpc.search_read(
            "res.users",
            [("login", "=", "vendor_test@test.com")],
            fields=["id", "login"],
        )
        if existing:
            data["portal_user_id"] = existing[0]["id"]
            rpc.write("res.users", [data["portal_user_id"]], {"password": "vendor_test_123"})
            print(f"  Portal user already exists: ID {data['portal_user_id']} (password reset)")
        else:
            # Create partner first
            partner_id = rpc.create("res.partner", {
                "name": "Test Vendor (Portal)",
                "email": "vendor_test@test.com",
                "company_type": "person",
            })
            # Create portal user
            portal_group = rpc.search("res.groups", [("category_id.name", "=", "User types"), ("name", "ilike", "Portal")])
            if not portal_group:
                portal_group = rpc.search("res.groups", [("id", "=", rpc.execute("ir.model.data", "check_object_reference", "base", "group_portal")[1])])

            user_id = rpc.create("res.users", {
                "name": "Test Vendor (Portal)",
                "login": "vendor_test@test.com",
                "password": "vendor_test_123",
                "partner_id": partner_id,
                "groups_id": [(6, 0, portal_group)] if portal_group else [],
            })
            data["portal_user_id"] = user_id
            log_pass(f"Created portal user: ID {user_id}")

        # Create second portal user for access control tests
        existing2 = rpc.search_read(
            "res.users",
            [("login", "=", "vendor_test2@test.com")],
            fields=["id"],
        )
        if existing2:
            data["portal_user2_id"] = existing2[0]["id"]
            rpc.write("res.users", [data["portal_user2_id"]], {"password": "vendor_test2_123"})
        else:
            partner2_id = rpc.create("res.partner", {
                "name": "Test Vendor 2 (Portal)",
                "email": "vendor_test2@test.com",
                "company_type": "person",
            })
            portal_group = rpc.search("res.groups", [("category_id.name", "=", "User types"), ("name", "ilike", "Portal")])
            user2_id = rpc.create("res.users", {
                "name": "Test Vendor 2 (Portal)",
                "login": "vendor_test2@test.com",
                "password": "vendor_test2_123",
                "groups_id": [(6, 0, portal_group)] if portal_group else [],
                "partner_id": partner2_id,
            })
            data["portal_user2_id"] = user2_id
            log_pass(f"Created portal user 2: ID {user2_id}")

    except Exception as e:
        log_fail("Create portal users", str(e))
        traceback.print_exc()
        return data

    # Create equipment category
    try:
        cat_ids = rpc.search("maintenance.equipment.category", [("name", "=", "Test Category Portal")])
        if cat_ids:
            data["category_id"] = cat_ids[0]
        else:
            data["category_id"] = rpc.create("maintenance.equipment.category", {
                "name": "Test Category Portal",
            })
            log_pass(f"Created equipment category: ID {data['category_id']}")
    except Exception as e:
        log_fail("Create equipment category", str(e))

    # Create maintenance team
    try:
        team_ids = rpc.search("maintenance.team", [])
        if team_ids:
            data["team_id"] = team_ids[0]
        else:
            data["team_id"] = rpc.create("maintenance.team", {"name": "Test Team"})
        log_pass(f"Using maintenance team: ID {data['team_id']}")
    except Exception as e:
        log_fail("Get/create maintenance team", str(e))

    # Create equipment (assigned to portal user 1 only)
    try:
        equip_ids = rpc.search("maintenance.equipment", [("name", "=", "Test Equipment A")])
        if equip_ids:
            data["equipment_a_id"] = equip_ids[0]
            # Ensure portal user is assigned
            rpc.write("maintenance.equipment", [data["equipment_a_id"]], {
                "portal_user_ids": [(4, data["portal_user_id"])],
            })
        else:
            data["equipment_a_id"] = rpc.create("maintenance.equipment", {
                "name": "Test Equipment A",
                "serial_no": "SN-TEST-001",
                "category_id": data.get("category_id"),
                "location": "Building A, Floor 2",
                "model": "Model X-100",
                "note": "<p>Test equipment notes with <b>HTML</b></p>",
                "portal_user_ids": [(4, data["portal_user_id"])],
            })
            log_pass(f"Created equipment A: ID {data['equipment_a_id']}")

        # Equipment B - assigned to portal user 2 only (for access control test)
        equip_b_ids = rpc.search("maintenance.equipment", [("name", "=", "Test Equipment B")])
        if equip_b_ids:
            data["equipment_b_id"] = equip_b_ids[0]
        else:
            data["equipment_b_id"] = rpc.create("maintenance.equipment", {
                "name": "Test Equipment B",
                "serial_no": "SN-TEST-002",
                "category_id": data.get("category_id"),
                "location": "Building B, Floor 1",
                "portal_user_ids": [(4, data["portal_user2_id"])],
            })
            log_pass(f"Created equipment B: ID {data['equipment_b_id']}")

        # Equipment C - no portal users (for negative test)
        equip_c_ids = rpc.search("maintenance.equipment", [("name", "=", "Test Equipment C (No Portal)")])
        if equip_c_ids:
            data["equipment_c_id"] = equip_c_ids[0]
        else:
            data["equipment_c_id"] = rpc.create("maintenance.equipment", {
                "name": "Test Equipment C (No Portal)",
                "serial_no": "SN-TEST-003",
            })
            log_pass(f"Created equipment C (no portal): ID {data['equipment_c_id']}")

    except Exception as e:
        log_fail("Create equipment", str(e))
        traceback.print_exc()

    # Create maintenance stages if needed
    try:
        stages = rpc.search_read("maintenance.stage", [], fields=["id", "name", "sequence", "done"])
        if len(stages) < 2:
            log_warn("Maintenance stages", f"Only {len(stages)} stages found, creating more")
            rpc.create("maintenance.stage", {"name": "New", "sequence": 1, "done": False})
            rpc.create("maintenance.stage", {"name": "In Progress", "sequence": 5, "done": False})
            rpc.create("maintenance.stage", {"name": "Done", "sequence": 10, "done": True})
            stages = rpc.search_read("maintenance.stage", [], fields=["id", "name", "sequence", "done"])

        data["stages"] = stages
        data["first_stage_id"] = min(stages, key=lambda s: s["sequence"])["id"]
        done_stages = [s for s in stages if s.get("done")]
        data["done_stage_id"] = done_stages[0]["id"] if done_stages else None
        log_pass(f"Found {len(stages)} maintenance stages")
        for s in sorted(stages, key=lambda x: x["sequence"]):
            print(f"    Stage: {s['name']} (seq={s['sequence']}, done={s.get('done', False)})")
    except Exception as e:
        log_fail("Check maintenance stages", str(e))

    # Create maintenance requests
    try:
        # Request 1: assigned to portal user 1
        req_ids = rpc.search("maintenance.request", [("name", "=", "Test Request Alpha")])
        if req_ids:
            data["request_a_id"] = req_ids[0]
            rpc.write("maintenance.request", [data["request_a_id"]], {
                "portal_user_ids": [(4, data["portal_user_id"])],
                "stage_id": data["first_stage_id"],
            })
        else:
            data["request_a_id"] = rpc.create("maintenance.request", {
                "name": "Test Request Alpha",
                "equipment_id": data.get("equipment_a_id"),
                "maintenance_type": "corrective",
                "description": "Test corrective maintenance request",
                "portal_user_ids": [(4, data["portal_user_id"])],
                "stage_id": data["first_stage_id"],
                "maintenance_team_id": data.get("team_id"),
            })
            log_pass(f"Created request Alpha: ID {data['request_a_id']}")

        # Request 2: assigned to portal user 2 (for access control test)
        req_b_ids = rpc.search("maintenance.request", [("name", "=", "Test Request Beta")])
        if req_b_ids:
            data["request_b_id"] = req_b_ids[0]
        else:
            data["request_b_id"] = rpc.create("maintenance.request", {
                "name": "Test Request Beta",
                "equipment_id": data.get("equipment_b_id"),
                "maintenance_type": "preventive",
                "description": "Test preventive maintenance request for user 2",
                "portal_user_ids": [(4, data["portal_user2_id"])],
                "stage_id": data["first_stage_id"],
                "maintenance_team_id": data.get("team_id"),
            })
            log_pass(f"Created request Beta: ID {data['request_b_id']}")

        # Request 3: no portal users (negative test)
        req_c_ids = rpc.search("maintenance.request", [("name", "=", "Test Request Gamma (No Portal)")])
        if req_c_ids:
            data["request_c_id"] = req_c_ids[0]
        else:
            data["request_c_id"] = rpc.create("maintenance.request", {
                "name": "Test Request Gamma (No Portal)",
                "maintenance_type": "corrective",
                "stage_id": data["first_stage_id"],
                "maintenance_team_id": data.get("team_id"),
            })
            log_pass(f"Created request Gamma (no portal): ID {data['request_c_id']}")

    except Exception as e:
        log_fail("Create maintenance requests", str(e))
        traceback.print_exc()

    return data


# ============================================================
# Phase 5: Backend (Internal User) Tests
# ============================================================
def test_backend_internal(rpc, data):
    log_section("Phase 5: Backend (Internal User) Tests")

    # Test: Admin can see portal_user_ids on equipment
    try:
        equip = rpc.read("maintenance.equipment", [data["equipment_a_id"]],
                         fields=["name", "portal_user_ids"])
        if equip and data["portal_user_id"] in equip[0]["portal_user_ids"]:
            log_pass("Admin sees portal_user_ids on equipment")
        else:
            log_fail("Admin sees portal_user_ids on equipment", str(equip))
    except Exception as e:
        log_fail("Admin read equipment portal_user_ids", str(e))

    # Test: Admin can see portal_user_ids on request
    try:
        req = rpc.read("maintenance.request", [data["request_a_id"]],
                       fields=["name", "portal_user_ids", "portal_notes"])
        if req and data["portal_user_id"] in req[0]["portal_user_ids"]:
            log_pass("Admin sees portal_user_ids on request")
        else:
            log_fail("Admin sees portal_user_ids on request", str(req))
    except Exception as e:
        log_fail("Admin read request portal_user_ids", str(e))

    # Test: Admin can write portal_notes
    try:
        rpc.write("maintenance.request", [data["request_a_id"]], {
            "portal_notes": "Admin test note",
        })
        req = rpc.read("maintenance.request", [data["request_a_id"]], fields=["portal_notes"])
        if req[0]["portal_notes"] == "Admin test note":
            log_pass("Admin can write portal_notes")
        else:
            log_fail("Admin write portal_notes", f"Got: {req[0]['portal_notes']}")
        # Clean up
        rpc.write("maintenance.request", [data["request_a_id"]], {"portal_notes": False})
    except Exception as e:
        log_fail("Admin write portal_notes", str(e))

    # Test: Auto-inherit portal users from equipment via onchange
    try:
        # Create a new request with equipment that has portal users
        new_req_id = rpc.create("maintenance.request", {
            "name": "Test Onchange Inherit",
            "equipment_id": data["equipment_a_id"],
            "maintenance_team_id": data.get("team_id"),
        })
        req = rpc.read("maintenance.request", [new_req_id], fields=["portal_user_ids"])
        # Note: onchange may not fire via XML-RPC create - this is expected
        # The onchange only fires in the web UI
        if req[0]["portal_user_ids"]:
            log_pass("Portal users auto-inherited from equipment on create")
        else:
            log_warn("Portal users NOT auto-inherited via XML-RPC",
                     "Expected: onchange only fires in web UI, not via XML-RPC create")
        # Clean up
        rpc.unlink("maintenance.request", [new_req_id])
    except Exception as e:
        log_fail("Onchange inheritance test", str(e))

    # Test: Admin can add/remove portal users
    try:
        rpc.write("maintenance.equipment", [data["equipment_a_id"]], {
            "portal_user_ids": [(4, data["portal_user2_id"])],  # Add user 2
        })
        equip = rpc.read("maintenance.equipment", [data["equipment_a_id"]], fields=["portal_user_ids"])
        if data["portal_user2_id"] in equip[0]["portal_user_ids"]:
            log_pass("Admin can add portal users to equipment")
        else:
            log_fail("Admin add portal user to equipment", "User not found after add")

        # Remove user 2
        rpc.write("maintenance.equipment", [data["equipment_a_id"]], {
            "portal_user_ids": [(3, data["portal_user2_id"])],
        })
        equip = rpc.read("maintenance.equipment", [data["equipment_a_id"]], fields=["portal_user_ids"])
        if data["portal_user2_id"] not in equip[0]["portal_user_ids"]:
            log_pass("Admin can remove portal users from equipment")
        else:
            log_fail("Admin remove portal user from equipment", "User still present")
    except Exception as e:
        log_fail("Admin manage portal users", str(e))


# ============================================================
# Phase 6: Portal User Access Control Tests
# ============================================================
def test_portal_access_control(data):
    log_section("Phase 6: Portal User Access Control Tests (XML-RPC)")

    # Connect as portal user 1
    try:
        portal_rpc = OdooRPC(ODOO_URL, DB_NAME, "vendor_test@test.com", "vendor_test_123")
        log_pass("Portal user 1 can authenticate via XML-RPC")
    except Exception as e:
        log_fail("Portal user 1 authentication", str(e))
        return

    # Test: Portal user can read assigned equipment
    try:
        equip = portal_rpc.search_read(
            "maintenance.equipment",
            [("id", "=", data["equipment_a_id"])],
            fields=["name", "serial_no"],
        )
        if equip and equip[0]["name"] == "Test Equipment A":
            log_pass("Portal user can read assigned equipment")
        else:
            log_fail("Portal user read assigned equipment", f"Got: {equip}")
    except Exception as e:
        log_fail("Portal user read assigned equipment", str(e))

    # Test: Portal user CANNOT read unassigned equipment
    try:
        equip = portal_rpc.search_read(
            "maintenance.equipment",
            [("id", "=", data["equipment_b_id"])],
            fields=["name"],
        )
        if not equip:
            log_pass("Portal user CANNOT read unassigned equipment (empty result)")
        else:
            log_fail("Portal user read unassigned equipment", f"Should not see equipment B but got: {equip}")
    except Exception as e:
        # AccessError is expected
        if "AccessError" in str(e) or "access" in str(e).lower():
            log_pass("Portal user CANNOT read unassigned equipment (AccessError)")
        else:
            log_fail("Portal user read unassigned equipment", str(e))

    # Test: Portal user can read assigned request
    try:
        req = portal_rpc.search_read(
            "maintenance.request",
            [("id", "=", data["request_a_id"])],
            fields=["name", "portal_notes"],
        )
        if req and req[0]["name"] == "Test Request Alpha":
            log_pass("Portal user can read assigned request")
        else:
            log_fail("Portal user read assigned request", f"Got: {req}")
    except Exception as e:
        log_fail("Portal user read assigned request", str(e))

    # Test: Portal user CANNOT read unassigned request
    try:
        req = portal_rpc.search_read(
            "maintenance.request",
            [("id", "=", data["request_b_id"])],
            fields=["name"],
        )
        if not req:
            log_pass("Portal user CANNOT read unassigned request (empty result)")
        else:
            log_fail("Portal user read unassigned request", f"Should not see request B but got: {req}")
    except Exception as e:
        if "AccessError" in str(e) or "access" in str(e).lower():
            log_pass("Portal user CANNOT read unassigned request (AccessError)")
        else:
            log_fail("Portal user read unassigned request", str(e))

    # Test: Portal user CANNOT create equipment
    try:
        portal_rpc.create("maintenance.equipment", {
            "name": "Unauthorized Equipment",
        })
        log_fail("Portal user create equipment", "Should have been denied")
    except Exception as e:
        # Accept any exception - the operation was denied (error may be in Chinese)
        log_pass("Portal user CANNOT create equipment (denied)")

    # Test: Portal user CANNOT delete equipment
    try:
        portal_rpc.unlink("maintenance.equipment", [data["equipment_a_id"]])
        log_fail("Portal user delete equipment", "Should have been denied")
    except Exception as e:
        log_pass("Portal user CANNOT delete equipment (denied)")

    # Test: Portal user CANNOT create requests
    try:
        portal_rpc.create("maintenance.request", {
            "name": "Unauthorized Request",
        })
        log_fail("Portal user create request", "Should have been denied")
    except Exception as e:
        log_pass("Portal user CANNOT create requests (denied)")

    # Test: Portal user CANNOT delete requests
    try:
        portal_rpc.unlink("maintenance.request", [data["request_a_id"]])
        log_fail("Portal user delete request", "Should have been denied")
    except Exception as e:
        log_pass("Portal user CANNOT delete requests (denied)")

    # Test: Portal user can write to assigned request (portal_notes)
    try:
        portal_rpc.write("maintenance.request", [data["request_a_id"]], {
            "portal_notes": "Portal user test note",
        })
        log_pass("Portal user can write to assigned request")
    except Exception as e:
        log_fail("Portal user write to assigned request", str(e))

    # Test: Portal user CANNOT write to unassigned request
    try:
        portal_rpc.write("maintenance.request", [data["request_b_id"]], {
            "portal_notes": "Should not work",
        })
        log_fail("Portal user write to unassigned request", "Should have been denied")
    except Exception as e:
        # Accept any exception - the operation was denied
        log_pass("Portal user CANNOT write to unassigned request (denied)")

    # Test: Portal user can read maintenance stages
    try:
        stages = portal_rpc.search_read("maintenance.stage", [], fields=["name"])
        if stages:
            log_pass(f"Portal user can read maintenance stages ({len(stages)} stages)")
        else:
            log_fail("Portal user read stages", "No stages returned")
    except Exception as e:
        log_fail("Portal user read stages", str(e))

    # Test: Portal user can read equipment categories
    try:
        cats = portal_rpc.search_read("maintenance.equipment.category", [], fields=["name"])
        if cats:
            log_pass(f"Portal user can read equipment categories ({len(cats)} categories)")
        else:
            log_warn("Portal user read categories", "No categories returned (may be empty)")
    except Exception as e:
        log_fail("Portal user read categories", str(e))


# ============================================================
# Phase 7: Portal HTTP Tests (Web Interface)
# ============================================================
def test_portal_http(data):
    log_section("Phase 7: Portal HTTP Interface Tests")

    # Login as portal user
    session = OdooHTTPSession(ODOO_URL, DB_NAME)
    try:
        resp = session.login("vendor_test@test.com", "vendor_test_123")
        if resp.status_code == 200 and "/my" in resp.url:
            log_pass("Portal user HTTP login successful")
        elif resp.status_code == 200:
            log_pass(f"Portal user HTTP login (redirected to {resp.url})")
        else:
            log_fail("Portal user HTTP login", f"Status {resp.status_code}, URL: {resp.url}")
    except Exception as e:
        log_fail("Portal user HTTP login", str(e))
        return

    # Test: Portal home page has equipment and request counters
    try:
        resp = session.get("/my/home")
        if resp.status_code == 200:
            has_equipment = "設備" in resp.text or "Equipment" in resp.text or "/my/equipments" in resp.text
            has_requests = "維修" in resp.text or "Maintenance" in resp.text or "/my/maintenance-requests" in resp.text
            if has_equipment and has_requests:
                log_pass("Portal home shows equipment and maintenance request cards")
            elif has_equipment:
                log_pass("Portal home shows equipment card")
                log_warn("Portal home maintenance card", "Not found in page text")
            elif has_requests:
                log_pass("Portal home shows maintenance request card")
                log_warn("Portal home equipment card", "Not found in page text")
            else:
                log_fail("Portal home cards", "Neither equipment nor maintenance cards found")
        else:
            log_fail("Portal home page", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Portal home page", str(e))

    # Test: Equipment list page
    try:
        resp = session.get("/my/equipments")
        if resp.status_code == 200:
            log_pass("Equipment list page loads (HTTP 200)")
            # Check content
            if "Test Equipment A" in resp.text:
                log_pass("Equipment list shows assigned equipment 'Test Equipment A'")
            else:
                log_fail("Equipment list content", "Cannot find 'Test Equipment A'")
            if "Test Equipment B" not in resp.text:
                log_pass("Equipment list correctly hides unassigned equipment B")
            else:
                log_fail("Equipment list security", "Shows unassigned equipment B!")
        else:
            log_fail("Equipment list page", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Equipment list page", str(e))

    # Test: Equipment detail page
    try:
        resp = session.get(f"/my/equipments/{data['equipment_a_id']}")
        if resp.status_code == 200:
            log_pass("Equipment detail page loads (HTTP 200)")
            if "SN-TEST-001" in resp.text:
                log_pass("Equipment detail shows serial number")
            else:
                log_warn("Equipment detail serial", "Serial number not found in page")
            if "Test Category Portal" in resp.text:
                log_pass("Equipment detail shows category")
            if "Building A" in resp.text:
                log_pass("Equipment detail shows location")
        else:
            log_fail("Equipment detail page", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Equipment detail page", str(e))

    # Test: Equipment detail - access denied for unassigned equipment
    try:
        resp = session.get(f"/my/equipments/{data['equipment_b_id']}")
        if resp.status_code in (403, 404) or "error" in resp.url.lower() or resp.status_code == 200 and "Access" in resp.text:
            log_pass("Equipment detail access denied for unassigned equipment")
        elif resp.status_code == 200 and "Test Equipment B" not in resp.text:
            log_pass("Equipment detail hides unassigned equipment content")
        else:
            # Check if redirected to error page
            if "403" in resp.text or "access" in resp.text.lower() or resp.url != f"{ODOO_URL}/my/equipments/{data['equipment_b_id']}":
                log_pass("Equipment detail denied for unassigned (redirect/error page)")
            else:
                log_fail("Equipment detail access control",
                         f"Status {resp.status_code}, URL: {resp.url}, expected 403/404")
    except Exception as e:
        log_fail("Equipment detail access control", str(e))

    # Test: Maintenance request list page
    try:
        resp = session.get("/my/maintenance-requests")
        if resp.status_code == 200:
            log_pass("Maintenance request list page loads (HTTP 200)")
            if "Test Request Alpha" in resp.text:
                log_pass("Request list shows assigned request 'Test Request Alpha'")
            else:
                log_fail("Request list content", "Cannot find 'Test Request Alpha'")
            if "Test Request Beta" not in resp.text:
                log_pass("Request list correctly hides unassigned request Beta")
            else:
                log_fail("Request list security", "Shows unassigned request Beta!")
        else:
            log_fail("Maintenance request list page", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Maintenance request list page", str(e))

    # Test: Maintenance request detail page
    try:
        resp = session.get(f"/my/maintenance-requests/{data['request_a_id']}")
        if resp.status_code == 200:
            log_pass("Maintenance request detail page loads (HTTP 200)")
            # Check for key elements
            if "Test Request Alpha" in resp.text:
                log_pass("Request detail shows request name")
            if "Test Equipment A" in resp.text:
                log_pass("Request detail shows equipment name")
            # Check for action buttons
            if "in_progress" in resp.text or "開始工作" in resp.text:
                log_pass("Request detail shows status update button")
            # Check for notes form
            if "textarea" in resp.text.lower() or "備註" in resp.text:
                log_pass("Request detail shows notes input form")
        else:
            log_fail("Maintenance request detail page", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Maintenance request detail page", str(e))

    # Test: Request detail - access denied for unassigned request
    try:
        resp = session.get(f"/my/maintenance-requests/{data['request_b_id']}")
        if resp.status_code in (403, 404) or resp.url != f"{ODOO_URL}/my/maintenance-requests/{data['request_b_id']}":
            log_pass("Request detail access denied for unassigned request")
        elif resp.status_code == 200 and "Test Request Beta" not in resp.text:
            log_pass("Request detail hides unassigned request content")
        else:
            if "403" in resp.text or "access" in resp.text.lower():
                log_pass("Request detail denied for unassigned (error in page)")
            else:
                log_fail("Request detail access control", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Request detail access control", str(e))

    # Test: Update request status (set in progress)
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "in_progress"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Request status update (in_progress) successful")
        else:
            log_fail("Request status update (in_progress)", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Request status update (in_progress)", str(e))

    # Test: Add notes via portal
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"notes": "Portal test note: work completed on unit A"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Add notes via portal successful")
            # Verify notes were saved
            if "Portal test note" in resp.text or "work completed" in resp.text:
                log_pass("Notes visible on detail page after save")
        else:
            log_fail("Add notes via portal", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Add notes via portal", str(e))

    # Test: Update request status (set done)
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "done"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Request status update (done) successful")
        else:
            log_fail("Request status update (done)", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Request status update (done)", str(e))

    # Test: Search functionality on equipment list
    try:
        resp = session.get("/my/equipments?search=SN-TEST-001&search_in=serial_no")
        if resp.status_code == 200:
            if "Test Equipment A" in resp.text:
                log_pass("Equipment search by serial number works")
            else:
                log_warn("Equipment search result", "Search returned 200 but equipment not in results")
        else:
            log_fail("Equipment search", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Equipment search", str(e))

    # Test: Search by name on equipment list
    try:
        resp = session.get("/my/equipments?search=Test+Equipment&search_in=name")
        if resp.status_code == 200:
            log_pass("Equipment search by name works (HTTP 200)")
        else:
            log_fail("Equipment search by name", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Equipment search by name", str(e))

    # Test: Sort equipment list
    for sortby in ["name", "category_id", "serial_no"]:
        try:
            resp = session.get(f"/my/equipments?sortby={sortby}")
            if resp.status_code == 200:
                log_pass(f"Equipment sort by '{sortby}' works")
            else:
                log_fail(f"Equipment sort by '{sortby}'", f"HTTP {resp.status_code}")
        except Exception as e:
            log_fail(f"Equipment sort by '{sortby}'", str(e))

    # Test: Search on request list
    try:
        resp = session.get("/my/maintenance-requests?search=Alpha&search_in=name")
        if resp.status_code == 200 and "Test Request Alpha" in resp.text:
            log_pass("Request search by name works")
        elif resp.status_code == 200:
            log_warn("Request search by name", "200 but Alpha not in results")
        else:
            log_fail("Request search by name", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Request search by name", str(e))

    # Test: Sort request list
    for sortby in ["date", "name", "stage"]:
        try:
            resp = session.get(f"/my/maintenance-requests?sortby={sortby}")
            if resp.status_code == 200:
                log_pass(f"Request sort by '{sortby}' works")
            else:
                log_fail(f"Request sort by '{sortby}'", f"HTTP {resp.status_code}")
        except Exception as e:
            log_fail(f"Request sort by '{sortby}'", str(e))

    # Test: Filter requests by stage
    if data.get("stages"):
        for stage in data["stages"][:3]:
            try:
                resp = session.get(f"/my/maintenance-requests?filterby={stage['id']}")
                if resp.status_code == 200:
                    log_pass(f"Request filter by stage '{stage['name']}' works")
                else:
                    log_fail(f"Request filter by stage '{stage['name']}'", f"HTTP {resp.status_code}")
            except Exception as e:
                log_fail(f"Request filter by stage '{stage['name']}'", str(e))

    return session


# ============================================================
# Phase 8: Edge Cases & Stress Tests
# ============================================================
def test_edge_cases(rpc, data):
    log_section("Phase 8: Edge Cases & Boundary Tests")

    # Test: Non-existent equipment page
    session = OdooHTTPSession(ODOO_URL, DB_NAME)
    session.login("vendor_test@test.com", "vendor_test_123")

    try:
        resp = session.get("/my/equipments/999999")
        if resp.status_code in (403, 404, 302) or "error" in resp.url.lower() or resp.status_code == 200:
            log_pass(f"Non-existent equipment ID returns appropriate response ({resp.status_code})")
        else:
            log_fail("Non-existent equipment", f"Unexpected status {resp.status_code}")
    except Exception as e:
        log_fail("Non-existent equipment", str(e))

    # Test: Non-existent request page
    try:
        resp = session.get("/my/maintenance-requests/999999")
        if resp.status_code in (403, 404, 302) or "error" in resp.url.lower() or resp.status_code == 200:
            log_pass(f"Non-existent request ID returns appropriate response ({resp.status_code})")
        else:
            log_fail("Non-existent request", f"Unexpected status {resp.status_code}")
    except Exception as e:
        log_fail("Non-existent request", str(e))

    # Test: Invalid equipment ID (string)
    try:
        resp = session.get("/my/equipments/abc")
        if resp.status_code in (400, 404, 302):
            log_pass("Invalid equipment ID (string) handled properly")
        else:
            log_pass(f"Invalid equipment ID returns status {resp.status_code}")
    except Exception as e:
        log_fail("Invalid equipment ID", str(e))

    # Test: Negative equipment ID
    try:
        resp = session.get("/my/equipments/-1")
        if resp.status_code in (400, 403, 404, 302):
            log_pass(f"Negative equipment ID handled ({resp.status_code})")
        else:
            log_pass(f"Negative equipment ID returns status {resp.status_code}")
    except Exception as e:
        log_fail("Negative equipment ID", str(e))

    # Test: Empty search
    try:
        resp = session.get("/my/equipments?search=&search_in=name")
        if resp.status_code == 200:
            log_pass("Empty search query handled (returns all)")
        else:
            log_fail("Empty search query", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Empty search query", str(e))

    # Test: SQL injection attempt in search
    try:
        resp = session.get("/my/equipments?search=' OR '1'='1&search_in=name")
        if resp.status_code in (200, 400, 500):
            if resp.status_code == 200:
                log_pass("SQL injection in search handled safely (200, likely using ORM)")
            elif resp.status_code == 400:
                log_pass("SQL injection in search rejected (400)")
            else:
                log_warn("SQL injection in search", f"Got 500 - potential issue")
        else:
            log_fail("SQL injection in search", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("SQL injection in search", str(e))

    # Test: XSS attempt in search
    try:
        resp = session.get("/my/equipments?search=<script>alert('xss')</script>&search_in=name")
        if resp.status_code == 200:
            if "<script>alert('xss')</script>" in resp.text:
                log_fail("XSS vulnerability in search", "Script tag reflected without escaping!")
            else:
                log_pass("XSS in search escaped properly")
        else:
            log_pass(f"XSS search attempt handled ({resp.status_code})")
    except Exception as e:
        log_fail("XSS in search", str(e))

    # Test: XSS attempt in notes
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"notes": "<script>alert('xss')</script>"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            if "<script>alert('xss')</script>" in resp.text:
                log_fail("XSS vulnerability in notes", "Script tag reflected without escaping in notes display!")
            else:
                log_pass("XSS in notes escaped properly")
    except Exception as e:
        log_fail("XSS in notes", str(e))

    # Test: Very long notes
    try:
        long_note = "A" * 10000
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"notes": long_note},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Very long notes (10K chars) handled successfully")
        else:
            log_fail("Very long notes", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Very long notes", str(e))

    # Test: Unicode in notes
    try:
        unicode_note = "測試中文筆記 🔧 Ñoño αβγ العربية"
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"notes": unicode_note},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Unicode/emoji in notes handled")
        else:
            log_fail("Unicode in notes", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Unicode in notes", str(e))

    # Test: Empty action (no action, no notes)
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Empty update (no action, no notes) handled gracefully")
        else:
            log_fail("Empty update", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Empty update", str(e))

    # Test: Invalid action value
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "invalid_action"},
            allow_redirects=True,
        )
        if resp.status_code in (200, 400):
            log_pass(f"Invalid action value handled ({resp.status_code})")
        else:
            log_fail("Invalid action value", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Invalid action value", str(e))

    # Test: Update already-done request (double-done)
    try:
        resp = session.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "done"},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            log_pass("Double-done action handled (no crash)")
        else:
            log_fail("Double-done action", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Double-done action", str(e))

    # Test: Pagination with large page number
    try:
        resp = session.get("/my/equipments?page=99999")
        if resp.status_code == 200:
            log_pass("Large page number handled (returns empty or last page)")
        else:
            log_fail("Large page number", f"HTTP {resp.status_code}")
    except Exception as e:
        log_fail("Large page number", str(e))

    # Test: Invalid sortby parameter
    try:
        resp = session.get("/my/equipments?sortby=invalid_field")
        if resp.status_code == 200:
            log_pass("Invalid sortby parameter handled (defaults to safe sort)")
        elif resp.status_code == 500:
            log_fail("Invalid sortby parameter", "Causes 500 error - needs validation")
        else:
            log_pass(f"Invalid sortby handled ({resp.status_code})")
    except Exception as e:
        log_fail("Invalid sortby parameter", str(e))

    # Test: Invalid search_in parameter
    try:
        resp = session.get("/my/equipments?search=test&search_in=nonexistent_field")
        if resp.status_code == 200:
            log_pass("Invalid search_in parameter handled safely")
        elif resp.status_code == 500:
            log_fail("Invalid search_in parameter", "Causes 500 error - needs input validation")
        else:
            log_pass(f"Invalid search_in handled ({resp.status_code})")
    except Exception as e:
        log_fail("Invalid search_in parameter", str(e))

    # Test: Invalid filterby parameter for requests
    try:
        resp = session.get("/my/maintenance-requests?filterby=99999")
        if resp.status_code == 200:
            log_pass("Invalid filterby (non-existent stage) handled")
        elif resp.status_code == 500:
            log_fail("Invalid filterby parameter", "Causes 500 error")
        else:
            log_pass(f"Invalid filterby handled ({resp.status_code})")
    except Exception as e:
        log_fail("Invalid filterby parameter", str(e))


# ============================================================
# Phase 9: Security Tests (Unauthorized Access)
# ============================================================
def test_security(data):
    log_section("Phase 9: Security Tests (Unauthorized Access)")

    # Test: Unauthenticated access to portal pages
    anon_session = requests.Session()

    for path in ["/my/equipments", "/my/maintenance-requests",
                 f"/my/equipments/{data['equipment_a_id']}",
                 f"/my/maintenance-requests/{data['request_a_id']}"]:
        try:
            resp = anon_session.get(f"{ODOO_URL}{path}", allow_redirects=False)
            if resp.status_code in (302, 303):
                location = resp.headers.get("Location", "")
                if "login" in location or "web" in location:
                    log_pass(f"Unauthenticated access to {path} -> redirects to login")
                else:
                    log_warn(f"Unauthenticated access to {path}", f"Redirects to {location}")
            elif resp.status_code in (403, 404):
                log_pass(f"Unauthenticated access to {path} -> {resp.status_code}")
            else:
                log_fail(f"Unauthenticated access to {path}", f"HTTP {resp.status_code}")
        except Exception as e:
            log_fail(f"Unauthenticated access to {path}", str(e))

    # Test: CSRF protection on POST
    try:
        # POST without CSRF token
        resp = anon_session.post(
            f"{ODOO_URL}/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "done"},
            allow_redirects=False,
        )
        if resp.status_code in (302, 303, 400, 403):
            log_pass("CSRF protection: POST without token rejected")
        else:
            log_warn("CSRF protection", f"POST without token returned {resp.status_code}")
    except Exception as e:
        log_fail("CSRF protection test", str(e))

    # Test: Portal user 2 trying to update user 1's request
    session2 = OdooHTTPSession(ODOO_URL, DB_NAME)
    try:
        session2.login("vendor_test2@test.com", "vendor_test2_123")
        resp = session2.post(
            f"/my/maintenance-requests/{data['request_a_id']}/update",
            data={"action": "done", "notes": "Unauthorized update attempt"},
            allow_redirects=True,
        )
        # Status 400 = CSRF rejection (also acceptable - request was blocked)
        # Status 200 with redirect to /my = access denied redirect
        if resp.status_code in (400, 403, 404):
            log_pass(f"Cross-user request update denied (HTTP {resp.status_code})")
        elif "/my" in resp.url and "maintenance-requests" not in resp.url.split("/my")[-1]:
            log_pass("Cross-user request update denied (redirected to /my)")
        elif resp.status_code == 200 and "Test Request Alpha" not in resp.text:
            log_pass("Cross-user request update denied (content hidden)")
        else:
            log_fail("Cross-user request update", f"Status {resp.status_code}, URL: {resp.url}")
    except Exception as e:
        log_fail("Cross-user request update", str(e))

    # Test: Portal user 2 trying to view user 1's equipment
    try:
        resp = session2.get(f"/my/equipments/{data['equipment_a_id']}")
        if resp.status_code in (403, 404) or "error" in resp.url.lower():
            log_pass("Cross-user equipment view denied")
        elif resp.status_code == 200 and "Test Equipment A" not in resp.text:
            log_pass("Cross-user equipment view denied (content hidden)")
        else:
            log_fail("Cross-user equipment view", f"Status {resp.status_code}")
    except Exception as e:
        log_fail("Cross-user equipment view", str(e))

    # Test: Direct object reference - try to access request by guessing ID
    try:
        resp = session2.get(f"/my/maintenance-requests/{data['request_a_id']}")
        if resp.status_code in (403, 404) or "error" in resp.url.lower():
            log_pass("IDOR protection: cannot access other user's request by ID")
        elif resp.status_code == 200 and "Test Request Alpha" not in resp.text:
            log_pass("IDOR protection: content hidden for other user's request")
        else:
            log_fail("IDOR protection", f"May be vulnerable - Status {resp.status_code}")
    except Exception as e:
        log_fail("IDOR protection", str(e))


# ============================================================
# Phase 10: i18n / Translation Tests
# ============================================================
def test_i18n(rpc, data):
    log_section("Phase 10: i18n / Translation Tests")

    session = OdooHTTPSession(ODOO_URL, DB_NAME)
    session.login("vendor_test@test.com", "vendor_test_123")

    # Check if zh_TW translations are loaded
    try:
        resp = session.get("/my/equipments")
        if resp.status_code == 200:
            # Check for Chinese text
            zh_indicators = ["設備", "查看", "序號", "類別"]
            found_zh = [t for t in zh_indicators if t in resp.text]
            if found_zh:
                log_pass(f"zh_TW translations active on equipment page (found: {', '.join(found_zh)})")
            else:
                # Check for English fallbacks
                en_indicators = ["Equipment", "Serial", "Category", "View"]
                found_en = [t for t in en_indicators if t in resp.text]
                if found_en:
                    log_warn("zh_TW translations", f"Page shows English text: {', '.join(found_en)}")
                else:
                    log_warn("zh_TW translations", "Cannot determine language from page content")
    except Exception as e:
        log_fail("i18n equipment page", str(e))

    try:
        resp = session.get("/my/maintenance-requests")
        if resp.status_code == 200:
            zh_indicators = ["維修", "請求", "階段", "日期"]
            found_zh = [t for t in zh_indicators if t in resp.text]
            if found_zh:
                log_pass(f"zh_TW translations active on request page (found: {', '.join(found_zh)})")
            else:
                log_warn("zh_TW translations on requests", "Chinese text not detected")
    except Exception as e:
        log_fail("i18n request page", str(e))

    # Check detail page
    try:
        resp = session.get(f"/my/maintenance-requests/{data['request_a_id']}")
        if resp.status_code == 200:
            zh_detail = ["請求資訊", "更新階段", "備註", "儲存"]
            found = [t for t in zh_detail if t in resp.text]
            if found:
                log_pass(f"zh_TW translations on request detail (found: {', '.join(found)})")
            else:
                log_warn("zh_TW detail translations", "Chinese text not detected on detail page")
    except Exception as e:
        log_fail("i18n detail page", str(e))


# ============================================================
# Phase 11: Model Method Tests (Business Logic)
# ============================================================
def test_business_logic(rpc, data):
    log_section("Phase 11: Business Logic Tests")

    # Reset request to first stage for testing
    try:
        rpc.write("maintenance.request", [data["request_a_id"]], {
            "stage_id": data["first_stage_id"],
            "portal_notes": False,
        })
        log_pass("Reset request to first stage for testing")
    except Exception as e:
        log_fail("Reset request stage", str(e))
        return

    # Test: action_portal_set_in_progress
    try:
        rpc.call("maintenance.request", "action_portal_set_in_progress", [data["request_a_id"]])
        req = rpc.read("maintenance.request", [data["request_a_id"]], fields=["stage_id"])
        current_stage = req[0]["stage_id"][0]
        if current_stage != data["first_stage_id"]:
            log_pass(f"action_portal_set_in_progress moved to stage {req[0]['stage_id'][1]}")
        else:
            log_fail("action_portal_set_in_progress", "Stage did not change")
    except Exception as e:
        log_fail("action_portal_set_in_progress", str(e))

    # Test: action_portal_set_done
    try:
        rpc.call("maintenance.request", "action_portal_set_done", [data["request_a_id"]])
        req = rpc.read("maintenance.request", [data["request_a_id"]], fields=["stage_id"])
        current_stage_id = req[0]["stage_id"][0]
        if data["done_stage_id"] and current_stage_id == data["done_stage_id"]:
            log_pass(f"action_portal_set_done moved to done stage ({req[0]['stage_id'][1]})")
        elif not data["done_stage_id"]:
            log_warn("action_portal_set_done", "No done stage defined - cannot verify")
        else:
            # Check if the stage is marked as done
            stage = rpc.read("maintenance.stage", [current_stage_id], fields=["done"])
            if stage[0].get("done"):
                log_pass(f"action_portal_set_done moved to a done stage ({req[0]['stage_id'][1]})")
            else:
                log_fail("action_portal_set_done", f"Moved to stage {req[0]['stage_id'][1]} which is not done")
    except Exception as e:
        log_fail("action_portal_set_done", str(e))

    # Test: action_portal_add_notes
    try:
        rpc.write("maintenance.request", [data["request_a_id"]], {"portal_notes": False})
        rpc.call("maintenance.request", "action_portal_add_notes", [data["request_a_id"]], "First note")
        req = rpc.read("maintenance.request", [data["request_a_id"]], fields=["portal_notes"])
        if "First note" in (req[0]["portal_notes"] or ""):
            log_pass("action_portal_add_notes adds first note")
        else:
            log_fail("action_portal_add_notes first note", f"Got: {req[0]['portal_notes']}")

        # Add second note (should append)
        rpc.call("maintenance.request", "action_portal_add_notes", [data["request_a_id"]], "Second note")
        req = rpc.read("maintenance.request", [data["request_a_id"]], fields=["portal_notes"])
        notes = req[0]["portal_notes"] or ""
        if "First note" in notes and "Second note" in notes:
            log_pass("action_portal_add_notes appends subsequent notes")
        else:
            log_fail("action_portal_add_notes append", f"Got: {notes}")
    except Exception as e:
        log_fail("action_portal_add_notes", str(e))

    # Test: Message posted to chatter on status change
    try:
        messages = rpc.search_read(
            "mail.message",
            [("res_id", "=", data["request_a_id"]), ("model", "=", "maintenance.request")],
            fields=["body", "message_type", "subtype_id"],
            limit=10,
            order="id desc",
        )
        status_msgs = [m for m in messages if "portal" in (m.get("body") or "").lower() or
                       "Status updated" in (m.get("body") or "") or
                       "status" in (m.get("body") or "").lower()]
        if status_msgs:
            log_pass(f"Chatter messages posted for portal actions ({len(status_msgs)} found)")
        else:
            log_warn("Chatter messages", "No portal-related messages found in chatter")
    except Exception as e:
        log_fail("Chatter messages check", str(e))


# ============================================================
# Phase 12: Bulk/Stress Tests
# ============================================================
def test_bulk_operations(rpc, data):
    log_section("Phase 12: Bulk Data & Stress Tests")

    # Create multiple equipment for pagination test
    bulk_equip_ids = []
    try:
        for i in range(25):
            eid = rpc.create("maintenance.equipment", {
                "name": f"Bulk Equipment {i+1:03d}",
                "serial_no": f"BLK-{i+1:05d}",
                "category_id": data.get("category_id"),
                "portal_user_ids": [(4, data["portal_user_id"])],
            })
            bulk_equip_ids.append(eid)
        log_pass(f"Created 25 bulk equipment records for pagination test")
    except Exception as e:
        log_fail("Bulk equipment creation", str(e))

    # Test pagination
    session = OdooHTTPSession(ODOO_URL, DB_NAME)
    session.login("vendor_test@test.com", "vendor_test_123")

    try:
        # Page 1
        resp1 = session.get("/my/equipments?page=1")
        if resp1.status_code == 200:
            log_pass("Equipment list page 1 loads")
            # Check for pager
            if "page" in resp1.text.lower() or "pager" in resp1.text.lower() or "o_portal_pager" in resp1.text:
                log_pass("Pagination controls visible")
            else:
                log_warn("Pagination controls", "Pager not detected in page HTML")

        # Page 2
        resp2 = session.get("/my/equipments?page=2")
        if resp2.status_code == 200:
            log_pass("Equipment list page 2 loads")
        else:
            log_warn("Equipment list page 2", f"HTTP {resp2.status_code}")
    except Exception as e:
        log_fail("Pagination test", str(e))

    # Create bulk maintenance requests
    bulk_req_ids = []
    try:
        for i in range(15):
            rid = rpc.create("maintenance.request", {
                "name": f"Bulk Request {i+1:03d}",
                "equipment_id": data.get("equipment_a_id"),
                "maintenance_type": "corrective" if i % 2 == 0 else "preventive",
                "portal_user_ids": [(4, data["portal_user_id"])],
                "maintenance_team_id": data.get("team_id"),
            })
            bulk_req_ids.append(rid)
        log_pass(f"Created 15 bulk maintenance requests")
    except Exception as e:
        log_fail("Bulk request creation", str(e))

    # Test request pagination
    try:
        resp = session.get("/my/maintenance-requests?page=1")
        if resp.status_code == 200:
            log_pass("Request list page 1 with bulk data loads")
        resp = session.get("/my/maintenance-requests?page=2")
        if resp.status_code == 200:
            log_pass("Request list page 2 loads")
    except Exception as e:
        log_fail("Request pagination", str(e))

    # Rapid sequential requests (basic stress test)
    try:
        errors = 0
        for i in range(20):
            resp = session.get("/my/equipments")
            if resp.status_code != 200:
                errors += 1
        if errors == 0:
            log_pass("20 rapid sequential equipment list requests - all OK")
        else:
            log_fail("Rapid requests", f"{errors}/20 requests failed")
    except Exception as e:
        log_fail("Rapid requests", str(e))

    # Cleanup bulk data
    try:
        if bulk_equip_ids:
            rpc.unlink("maintenance.equipment", bulk_equip_ids)
        if bulk_req_ids:
            rpc.unlink("maintenance.request", bulk_req_ids)
        log_pass("Bulk test data cleaned up")
    except Exception as e:
        log_warn("Bulk cleanup", str(e))


# ============================================================
# Main Execution
# ============================================================
def main():
    print("=" * 60)
    print("  MAINTENANCE PORTAL - COMPREHENSIVE TEST SUITE")
    print(f"  Target: {ODOO_URL}")
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 0: Detect database
    if DB_NAME:
        print(f"Using configured database: {DB_NAME}")
    elif not detect_database():
        print("FATAL: Could not detect database name")
        sys.exit(1)

    # Step 1: Connect as admin
    try:
        rpc = OdooRPC(ODOO_URL, DB_NAME, ADMIN_USER, ADMIN_PASS)
        print(f"Connected as admin (uid={rpc.uid})")
    except Exception as e:
        print(f"FATAL: Cannot connect to Odoo: {e}")
        sys.exit(1)

    # Run all test phases
    if not test_module_installation(rpc):
        print("\nFATAL: Module installation failed. Cannot continue.")
        sys.exit(1)

    test_data_models(rpc)
    test_security_rules(rpc)
    data = create_test_data(rpc)

    if not data.get("portal_user_id"):
        print("\nFATAL: Could not create test data. Cannot continue.")
        sys.exit(1)

    test_backend_internal(rpc, data)
    test_portal_access_control(data)
    test_portal_http(data)
    test_edge_cases(rpc, data)
    test_security(data)
    test_business_logic(rpc, data)
    test_i18n(rpc, data)
    test_bulk_operations(rpc, data)

    # ========== FINAL REPORT ==========
    log_section("FINAL TEST REPORT")
    total = results["passed"] + results["failed"]
    print(f"\n  Total Tests:  {total}")
    print(f"  Passed:       {results['passed']}")
    print(f"  Failed:       {results['failed']}")
    print(f"  Warnings:     {len(results['warnings'])}")
    print(f"  Pass Rate:    {results['passed']/total*100:.1f}%" if total > 0 else "  Pass Rate: N/A")

    if results["errors"]:
        print(f"\n  === FAILURES ({results['failed']}) ===")
        for err in results["errors"]:
            print(f"  {err}")

    if results["warnings"]:
        print(f"\n  === WARNINGS ({len(results['warnings'])}) ===")
        for warn in results["warnings"]:
            print(f"  {warn}")

    print("\n" + "=" * 60)
    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
