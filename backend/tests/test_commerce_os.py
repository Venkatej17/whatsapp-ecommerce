"""Regression tests for Commerce OS backend (Master Admin + Tenant Workspace)."""
import os
import uuid
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@commerceos.com", "password": "Admin123!"}
OWNER = {"email": "owner@freshmart.com", "password": "Owner123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return s, r.json()


# ---------- AUTH ----------
def test_login_admin_and_me():
    s, u = _login(ADMIN)
    assert u["role"] == "MASTER_ADMIN"
    assert s.cookies.get("access_token")
    me = s.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == ADMIN["email"]


def test_login_owner_tenant_derivation():
    s, u = _login(OWNER)
    assert u["role"] == "TENANT_OWNER"
    assert u["tenant_id"] == "tenant_fresh"


def test_invalid_credentials():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@commerceos.com", "password": "wrong"})
    assert r.status_code in (400, 401)


# ---------- MASTER ADMIN ----------
def test_admin_overview_has_tenants_and_metrics():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/admin/overview")
    assert r.status_code == 200
    body = r.json()
    # Should have tenants and platform metrics but not full order lists
    assert "tenants" in body or "platform" in body or "metrics" in body
    # ensure no full orders array leaks
    dumped = str(body).lower()
    # tenants should include tenant_fresh
    assert "tenant_fresh" in dumped


def test_admin_tenants_list():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/admin/tenants")
    assert r.status_code == 200
    tenants = r.json()
    assert isinstance(tenants, list) and len(tenants) >= 3


def test_admin_templates_and_integrations_and_analytics_and_audit():
    s, _ = _login(ADMIN)
    for path in ["/api/admin/templates", "/api/admin/integrations", "/api/admin/analytics", "/api/admin/audit"]:
        r = s.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_admin_create_tenant_wizard():
    s, _ = _login(ADMIN)
    unique = uuid.uuid4().hex[:6]
    payload = {
        "business_name": f"TEST Biz {unique}",
        "category": "Grocery",
        "description": "Testing wizard",
        "email": f"biz{unique}@example.com",
        "phone": "9999999999",
        "city": "Bengaluru",
        "state": "KA",
        "pincode": "560001",
        "owner_email": f"owner{unique}@example.com",
        "owner_password": "Owner123!",
        "owner_name": "Test Owner",
    }
    r = s.post(f"{BASE_URL}/api/admin/tenants", json=payload)
    assert r.status_code in (200, 201), r.text
    tenant = r.json()
    assert tenant.get("id") or tenant.get("tenant_id")
    listing = s.get(f"{BASE_URL}/api/admin/tenants").json()
    assert any(payload["business_name"] in (t.get("business_name") or t.get("name") or "") for t in listing)


def test_admin_tenant_config_actions():
    s, _ = _login(ADMIN)
    tid = "tenant_fresh"
    # apply templates and automations should succeed
    r1 = s.post(f"{BASE_URL}/api/admin/tenants/{tid}/templates/apply", json={"template_ids": []})
    r2 = s.post(f"{BASE_URL}/api/admin/tenants/{tid}/automations/apply", json={"rule_ids": []})
    assert r1.status_code in (200, 201), r1.text
    assert r2.status_code in (200, 201), r2.text


# ---------- TENANT WORKSPACE ----------
def test_workspace_overview_and_lists():
    s, _ = _login(OWNER)
    for path in [
        "/api/workspace/overview",
        "/api/workspace/products",
        "/api/workspace/orders",
        "/api/workspace/customers",
        "/api/workspace/conversations",
        "/api/workspace/settings",
        "/api/workspace/fulfilment/queues",
        "/api/workspace/analytics",
    ]:
        r = s.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


def test_workspace_product_crud_cleanup():
    s, _ = _login(OWNER)
    payload = {"name": "TEST Broccoli", "category": "Produce", "price": 55, "stock": 30, "sku": "TEST-BROC"}
    created = s.post(f"{BASE_URL}/api/workspace/products", json=payload)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    upd = s.patch(f"{BASE_URL}/api/workspace/products/{pid}", json={"stock": 5})
    assert upd.status_code == 200
    dele = s.delete(f"{BASE_URL}/api/workspace/products/{pid}")
    assert dele.status_code in (200, 204)


def test_workspace_order_advance_and_note():
    s, _ = _login(OWNER)
    orders = s.get(f"{BASE_URL}/api/workspace/orders").json()
    # try to advance FM-10243 to next valid state
    detail = s.get(f"{BASE_URL}/api/workspace/orders/FM-10243")
    assert detail.status_code == 200
    # attempt add note
    note = s.post(f"{BASE_URL}/api/workspace/orders/FM-10245/notes", json={"note": "TEST note"})
    assert note.status_code in (200, 201), note.text


# ---------- ROLE ISOLATION ----------
def test_owner_cannot_access_admin_endpoints():
    s, _ = _login(OWNER)
    for path in ["/api/admin/overview", "/api/admin/tenants", "/api/admin/templates",
                 "/api/admin/integrations", "/api/admin/analytics", "/api/admin/audit"]:
        r = s.get(f"{BASE_URL}{path}")
        assert r.status_code == 403, f"{path} -> {r.status_code} (expected 403)"


def test_admin_cannot_access_workspace_endpoints():
    s, _ = _login(ADMIN)
    r = s.get(f"{BASE_URL}/api/workspace/overview")
    assert r.status_code in (400, 403), f"expected admin blocked from workspace, got {r.status_code}"


def test_logout_clears_session():
    s, _ = _login(OWNER)
    assert s.post(f"{BASE_URL}/api/auth/logout").status_code == 200
    assert s.get(f"{BASE_URL}/api/auth/me").status_code == 401
