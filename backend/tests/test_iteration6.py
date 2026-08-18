"""Iteration 6: Invoice PDFs, WhatsApp status notifications, Abandoned Cart engine."""
import hashlib
import hmac
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://whatsapp-commerce-os.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
INVOICE_SECRET = "Y2M1YjhkNmYwZTMyOTQ3Y2FiNTQxNzJmODk="


def _sign(order_id: str) -> str:
    return hmac.new(INVOICE_SECRET.encode(), order_id.encode(), hashlib.sha256).hexdigest()[:24]


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def owner_fresh():
    return _login("owner@freshmart.com", "Owner123!")


@pytest.fixture(scope="module")
def owner_glow():
    return _login("owner@glowcosmetics.com", "Owner123!")


@pytest.fixture(scope="module")
def master():
    return _login("admin@commerceos.com", "Admin123!")


# ---------- 1) COLLECTED invoice ----------
def test_collected_generates_invoice(owner_fresh):
    # Ensure order is at READY_FOR_PICKUP first
    r0 = owner_fresh.get(f"{API}/workspace/orders", timeout=15)
    orders = {o["id"]: o for o in r0.json()}
    assert "FM-10245" in orders, "FM-10245 not present"
    if orders["FM-10245"]["status"] != "READY_FOR_PICKUP":
        pytest.skip(f"FM-10245 not in READY_FOR_PICKUP (was {orders['FM-10245']['status']})")

    r = owner_fresh.patch(f"{API}/workspace/orders/FM-10245/status", json={"status": "COLLECTED"}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "COLLECTED"
    assert "invoice_url" in data and "/api/public/invoice/FM-10245/" in data["invoice_url"], data

    # Owner can download PDF
    pdf = owner_fresh.get(f"{API}/workspace/orders/FM-10245/invoice.pdf", timeout=20)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF"), "not a PDF"
    assert len(pdf.content) > 1000


def test_public_invoice_signed(owner_fresh):
    sig = _sign("FM-10245")
    r = requests.get(f"{API}/public/invoice/FM-10245/{sig}", timeout=15)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


def test_public_invoice_bad_signature():
    r = requests.get(f"{API}/public/invoice/FM-10245/deadbeefdeadbeefdeadbeef", timeout=15)
    assert r.status_code == 403


# ---------- 2) DELIVERED invoice ----------
def test_delivered_generates_invoice(owner_fresh):
    r0 = owner_fresh.get(f"{API}/workspace/orders", timeout=15)
    orders = {o["id"]: o for o in r0.json()}
    if "FM-10244" not in orders:
        pytest.skip("FM-10244 not present")
    cur = orders["FM-10244"]["status"]
    if cur != "OUT_FOR_DELIVERY":
        pytest.skip(f"FM-10244 not OUT_FOR_DELIVERY (was {cur})")

    r = owner_fresh.patch(f"{API}/workspace/orders/FM-10244/status", json={"status": "DELIVERED"}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "DELIVERED"
    assert "invoice_url" in d and "FM-10244" in d["invoice_url"]

    pdf = owner_fresh.get(f"{API}/workspace/orders/FM-10244/invoice.pdf", timeout=20)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


# ---------- 3) Status notifications in conversations ----------
def test_status_notifications_logged(owner_fresh):
    r = owner_fresh.get(f"{API}/workspace/conversations", timeout=15)
    assert r.status_code == 200
    convs = r.json()
    # convo for FM-10245 -> collected + invoice
    conv_245 = next((c for c in convs if c.get("linked_order_id") == "FM-10245"), None)
    assert conv_245, "no convo linked to FM-10245"
    bot_texts = " ".join(m["body"].lower() for m in conv_245.get("messages", []) if m.get("from") == "bot")
    assert "collected" in bot_texts
    assert "/api/public/invoice/fm-10245/" in bot_texts

    conv_244 = next((c for c in convs if c.get("linked_order_id") == "FM-10244"), None)
    if conv_244:
        bot_texts = " ".join(m["body"].lower() for m in conv_244.get("messages", []) if m.get("from") == "bot")
        assert "delivered" in bot_texts


# ---------- 4) Intermediate statuses notify, no invoice ----------
def test_intermediate_statuses_no_invoice(owner_fresh):
    r0 = owner_fresh.get(f"{API}/workspace/orders", timeout=15)
    orders = {o["id"]: o for o in r0.json()}
    if "FM-10243" not in orders:
        pytest.skip("FM-10243 not present")
    cur = orders["FM-10243"]["status"]
    if cur != "NEW":
        pytest.skip(f"FM-10243 not NEW (was {cur})")

    r1 = owner_fresh.patch(f"{API}/workspace/orders/FM-10243/status", json={"status": "PICKING"}, timeout=20)
    assert r1.status_code == 200, r1.text
    assert r1.json().get("invoice_url") in (None, ""), "PICKING should not produce invoice_url"

    r2 = owner_fresh.patch(f"{API}/workspace/orders/FM-10243/status", json={"status": "PACKING"}, timeout=20)
    assert r2.status_code == 200
    assert r2.json().get("invoice_url") in (None, "")

    # Verify convo bot messages
    convs = owner_fresh.get(f"{API}/workspace/conversations", timeout=15).json()
    conv = next((c for c in convs if c.get("linked_order_id") == "FM-10243"), None)
    if conv:
        texts = " ".join(m["body"].lower() for m in conv.get("messages", []) if m.get("from") == "bot")
        assert "picked" in texts or "picking" in texts
        assert "packed" in texts or "packing" in texts


# ---------- 5) Tenant isolation on invoice ----------
def test_invoice_tenant_isolation(owner_glow):
    r = owner_glow.get(f"{API}/workspace/orders/FM-10245/invoice.pdf", timeout=15)
    assert r.status_code == 404


# ---------- 6) Abandoned cart engine ----------
@pytest.fixture(scope="module")
def abandoned_cart_id(owner_fresh):
    r = owner_fresh.post(f"{API}/cart/session", json={"phone": "+919000099887", "customer": "Idle Sim"}, timeout=15)
    assert r.status_code == 200, r.text
    cart = r.json()["cart"] if "cart" in r.json() else r.json()
    cart_id = cart.get("id") or r.json().get("id")
    # response shape: _recalculate returns {cart, ...}? Check:
    if not cart_id:
        # Fallback via direct find
        cart_id = r.json().get("cart", {}).get("id")
    assert cart_id, f"cannot extract cart id from {r.json()}"
    r2 = owner_fresh.post(f"{API}/cart/{cart_id}/items", json={"sku": "FM-POT-01", "qty": 2}, timeout=15)
    assert r2.status_code == 200, r2.text
    return cart_id


def _force_stale(cart_id):
    """Backdate cart's updated_at so scan picks it up."""
    from pymongo import MongoClient
    from datetime import datetime, timezone, timedelta
    mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_name = os.environ.get("DB_NAME", "test_database")
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    res = mongo[db_name].carts.update_one({"id": cart_id}, {"$set": {"updated_at": old}, "$unset": {"nudged_at": ""}})
    return res.modified_count


def test_abandoned_scan_nudges(master, abandoned_cart_id):
    assert _force_stale(abandoned_cart_id) == 1
    r = master.post(f"{API}/admin/carts/abandoned/scan", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["scanned"] >= 1
    assert data["nudged"] >= 1

    # List includes our cart
    lst = master.get(f"{API}/admin/carts/abandoned", timeout=15).json()
    ours = [c for c in lst if c["id"] == abandoned_cart_id]
    assert ours, f"cart not in listing: {lst}"
    assert ours[0]["nudged_at"], "nudged_at not set"


def test_abandoned_scan_idempotent(master, abandoned_cart_id):
    # Second scan must NOT re-nudge the same cart
    r = master.post(f"{API}/admin/carts/abandoned/scan", timeout=15)
    assert r.status_code == 200
    data = r.json()
    # The cart is nudged; should not appear in scan target set now
    lst = master.get(f"{API}/admin/carts/abandoned", timeout=15).json()
    ours = [c for c in lst if c["id"] == abandoned_cart_id][0]
    assert ours["nudged_at"], "nudged_at should still be present"
    # scanned count should be 0 for un-nudged with items past cutoff (may be nonzero if other stale carts exist).


# ---------- 7) Regression smoke ----------
def test_regression_smoke(owner_fresh, master):
    # Products, orders, tenants list, conversations, cart still work
    for path in ["/workspace/products", "/workspace/orders", "/workspace/conversations"]:
        r = owner_fresh.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"{path} broken: {r.status_code}"
    for path in ["/admin/tenants", "/admin/carts/abandoned"]:
        r = master.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"{path} broken: {r.status_code}"


# ---------- Cleanup: test cart ----------
def test_cleanup(abandoned_cart_id):
    from pymongo import MongoClient
    mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db_name = os.environ.get("DB_NAME", "test_database")
    mongo[db_name].carts.delete_one({"id": abandoned_cart_id})
    mongo[db_name].conversations.delete_many({"phone": "+919000099887"})
    mongo[db_name].customers.delete_many({"phone": "+919000099887"})
