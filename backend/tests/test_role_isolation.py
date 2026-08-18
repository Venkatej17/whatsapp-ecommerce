import os
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@commerceos.com", "password": "Admin123!"}
OWNER = {"email": "owner@freshmart.com", "password": "Owner123!"}


def login(credentials):
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/auth/login", json=credentials)
    assert response.status_code == 200
    return session, response.json()


def test_master_admin_scope_and_cookie():
    session, user = login(ADMIN)
    assert user["role"] == "MASTER_ADMIN"
    assert session.cookies.get("access_token")
    assert session.get(f"{BASE_URL}/api/admin/overview").status_code == 200
    assert session.get(f"{BASE_URL}/api/dashboard").status_code == 403


def test_owner_scope_and_tenant_derivation():
    session, user = login(OWNER)
    assert user["role"] == "TENANT_OWNER"
    assert user["tenant_id"] == "tenant_fresh"
    dashboard = session.get(f"{BASE_URL}/api/dashboard")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["tenant"]["id"] == "tenant_fresh"
    assert all(item["tenant_id"] == "tenant_fresh" for item in body["products"])
    assert session.get(f"{BASE_URL}/api/admin/overview").status_code == 403
    assert session.get(f"{BASE_URL}/api/dashboard", headers={"X-Tenant-ID": "tenant_glow"}).json()["tenant"]["id"] == "tenant_fresh"


def test_owner_product_and_order_operations():
    session, _ = login(OWNER)
    payload = {"name": "TEST Role Isolation Item", "category": "Produce", "price": 125, "stock": 12, "sku": "TEST-ROLE"}
    created = session.post(f"{BASE_URL}/api/products", json=payload)
    assert created.status_code == 201
    assert created.json()["tenant_id"] == "tenant_fresh"
    changed = session.patch(f"{BASE_URL}/api/orders/FM-10243/status", json={"status": "PICKING"})
    assert changed.status_code == 200 and changed.json()["status"] == "PICKING"
    assert session.patch(f"{BASE_URL}/api/orders/FM-10245/status", json={"status": "COMPLETED"}, headers={"X-Tenant-ID": "tenant_glow"}).status_code == 200


def test_logout_clears_session():
    session, _ = login(OWNER)
    assert session.post(f"{BASE_URL}/api/auth/logout").status_code == 200
    assert session.get(f"{BASE_URL}/api/auth/me").status_code == 401