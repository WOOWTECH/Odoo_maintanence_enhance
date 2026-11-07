# -*- coding: utf-8 -*-
"""Connection settings for the standalone end-to-end scripts in this folder.

These scripts drive a running Odoo instance over XML-RPC / HTTP. They are
NOT Odoo unit tests (they are not under ``tests/`` and are never loaded by
``--test-enable``). Credentials are read from the environment; nothing is
hardcoded:

    MP_E2E_URL               default http://localhost:9070
    MP_E2E_DB                default odoomaintain
    MP_E2E_ADMIN_LOGIN       default admin
    MP_E2E_ADMIN_PASSWORD    required
    MP_E2E_PORTAL1_LOGIN     default vendor_test@test.com
    MP_E2E_PORTAL1_PASSWORD  required (set on the portal user by the scripts)
    MP_E2E_PORTAL2_LOGIN     default vendor_test2@test.com
    MP_E2E_PORTAL2_PASSWORD  required (set on the portal user by the scripts)
"""
import os
import sys


def _get(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        sys.exit(f"Missing environment variable {name} (see scripts/e2e/e2e_config.py)")
    return value


URL = _get("MP_E2E_URL", "http://localhost:9070").rstrip("/")
DB = _get("MP_E2E_DB", "odoomaintain")
ADMIN_USER = _get("MP_E2E_ADMIN_LOGIN", "admin")
ADMIN_PASS = _get("MP_E2E_ADMIN_PASSWORD")
PORTAL_USER1_LOGIN = _get("MP_E2E_PORTAL1_LOGIN", "vendor_test@test.com")
PORTAL_USER1_PASS = _get("MP_E2E_PORTAL1_PASSWORD")
PORTAL_USER2_LOGIN = _get("MP_E2E_PORTAL2_LOGIN", "vendor_test2@test.com")
PORTAL_USER2_PASS = _get("MP_E2E_PORTAL2_PASSWORD")
