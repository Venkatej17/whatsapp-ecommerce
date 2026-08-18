import os
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def test_dashboard_tenant_isolation():
    fresh = requests.get(f"{BASE_URL}/api/dashboard", headers={"X-Tenant-ID": "tenant_fresh"})
    glow = requests.get(f"{BASE_URL}/api/dashboard", headers={"X-Tenant-ID": "tenant_glow"})
    assert fresh.status_code == 200 and glow.status_code == 200
    assert fresh.json()["tenant"]["id"] == "tenant_fresh"
    assert glow.json()["tenant"]["id"] == "tenant_glow"
    assert all(p["tenant_id"] == "tenant_fresh" for p in fresh.json()["products"])
    assert all(p["tenant_id"] == "tenant_glow" for p in glow.json()["products"])
    assert not set(p["id"] for p in fresh.json()["products"]) & set(p["id"] for p in glow.json()["products"])


def test_products_create_and_searchable_persistence():
    headers = {"X-Tenant-ID": "tenant_fresh"}
    payload = {"name": "TEST Regression Mangoes", "category": "Produce", "price": 125, "stock": 12, "sku": "TEST-MANGO"}
    created = requests.post(f"{BASE_URL}/api/products", headers=headers, json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == payload["name"] and body["tenant_id"] == "tenant_fresh"
    dashboard = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
    assert any(p["id"] == body["id"] and p["status"] == "Low stock" for p in dashboard.json()["products"])


def test_order_transition_and_cross_tenant_protection():
    headers = {"X-Tenant-ID": "tenant_fresh"}
    changed = requests.patch(f"{BASE_URL}/api/orders/FM-10243/status", headers=headers, json={"status": "PICKING"})
    assert changed.status_code == 200 and changed.json()["status"] == "PICKING"
    blocked = requests.patch(f"{BASE_URL}/api/orders/FM-10243/status", headers={"X-Tenant-ID": "tenant_glow"}, json={"status": "COMPLETED"})
    assert blocked.status_code == 404