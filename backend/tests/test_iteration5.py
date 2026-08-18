"""Iteration 5 tests: Meta creds save, onboarding doc, payment link in WhatsApp confirm, payment tenant isolation."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@commerceos.com", "password": "Admin123!"}
OWNER_FRESH = {"email": "owner@freshmart.com", "password": "Owner123!"}
OWNER_GLOW = {"email": "owner@glowcosmetics.com", "password": "Owner123!"}

SIM_PHONE = "+919888888888"
SIM_NAME = "Priya"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def owner_fresh_session():
    return _login(OWNER_FRESH)


@pytest.fixture(scope="module")
def owner_glow_session():
    return _login(OWNER_GLOW)


# =============================================================
# TEST 1: WhatsApp simulator confirm → Stripe payment link in reply
# =============================================================
_state = {"order_id": None, "intent_id": None, "phone": SIM_PHONE}


def _sim(admin, body):
    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate", json={
        "tenant_id": "tenant_fresh",
        "from_phone": SIM_PHONE,
        "from_name": SIM_NAME,
        "body": body,
    })
    assert r.status_code == 200, r.text
    return r.json()["reply"]


def test_simulator_flow_ends_with_stripe_payment_link(admin_session):
    _sim(admin_session, "hi")
    _sim(admin_session, "shop")
    reply_add = _sim(admin_session, "add FM-TOM-01 2")
    assert "added" in reply_add.lower() or "✅" in reply_add
    _sim(admin_session, "pickup")
    reply_confirm = _sim(admin_session, "confirm")

    assert "checkout.stripe.com" in reply_confirm, f"No Stripe link found in confirm reply: {reply_confirm}"
    assert "💳" in reply_confirm or "pay" in reply_confirm.lower()

    # Extract order id (format like FR-XXXXX)
    import re
    m = re.search(r"\*(FR-\d+)\*", reply_confirm)
    assert m, f"Order id not found in reply: {reply_confirm}"
    _state["order_id"] = m.group(1)

    # Pickup code should be present
    pc = re.search(r"\*PC[A-Z0-9]{4}\*", reply_confirm)
    assert pc, f"Pickup code not found: {reply_confirm}"


def test_order_has_payment_link_and_intent(owner_fresh_session):
    assert _state["order_id"], "prior test must run"
    r = owner_fresh_session.get(f"{BASE_URL}/api/workspace/orders/{_state['order_id']}")
    assert r.status_code == 200, r.text
    o = r.json()
    assert o.get("payment_link"), f"no payment_link on order: {o}"
    assert "checkout.stripe.com" in o["payment_link"]
    assert o.get("payment_provider") == "stripe"
    assert o.get("payment_intent_id"), "payment_intent_id missing"
    _state["intent_id"] = o["payment_intent_id"]


# =============================================================
# TEST 2: Meta creds save (tenant_glow)
# =============================================================
def test_save_meta_creds_returns_ok(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/admin/tenants/tenant_glow/whatsapp-creds", json={
        "phone_number_id": "123456789012345",
        "waba_id": "987654",
        "access_token": "EAAG_test_dummy",
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


def test_tenant_glow_reflects_creds_without_leaking_token(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/tenants/tenant_glow")
    assert r.status_code == 200
    t = r.json()
    wa = t.get("integrations", {}).get("whatsapp", {})
    assert wa.get("connected") is True
    assert wa.get("phone_number_id") == "123456789012345"
    # Raw access token must NOT appear anywhere in response
    body_text = r.text
    assert "EAAG_test_dummy" not in body_text, "Raw access token leaked in tenant response!"
    # Encrypted form should be there or hidden
    assert "access_token" not in wa or wa.get("access_token_enc") is not None or "access_token_enc" in wa


# =============================================================
# TEST 3: Onboarding doc
# =============================================================
def test_onboarding_doc_fresh_mart(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/tenants/tenant_fresh/onboarding-doc")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("tenant_name") == "Fresh Mart"
    md = data.get("markdown", "")
    assert "# Fresh Mart" in md
    assert "owner@freshmart.com" in md
    assert "20" in md  # delivery
    assert "500" in md  # free above
    assert "pickup" in md.lower()
    assert "payment" in md.lower()
    # starter catalog with at least 3 products (bullets under section 5)
    import re
    starter_section = md.split("## 5.")[-1].split("## 6.")[0] if "## 5." in md else md
    product_lines = re.findall(r"^- \*\*.+?\*\*", starter_section, flags=re.MULTILINE)
    assert len(product_lines) >= 3, f"expected ≥3 products, got {len(product_lines)}: {product_lines}"


# =============================================================
# TEST 4: Payment intent tenant isolation
# =============================================================
def test_glow_cannot_access_fresh_payment_intent(owner_glow_session):
    assert _state["intent_id"], "need intent id from prior test"
    r = owner_glow_session.get(f"{BASE_URL}/api/workspace/payments/status/{_state['intent_id']}")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_fresh_owner_can_access_own_intent(owner_fresh_session):
    assert _state["intent_id"]
    r = owner_fresh_session.get(f"{BASE_URL}/api/workspace/payments/status/{_state['intent_id']}")
    # 200 (fetch stripe status) is expected
    assert r.status_code == 200, r.text


# =============================================================
# Cleanup — runs last (alphabetical): use a session-scoped finalizer
# =============================================================
@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end(request, admin_session):
    yield
    # Clean up created data via direct pymongo
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        cli = MongoClient(mongo_url)
        db = cli[db_name]
        if _state["order_id"]:
            # restore stock: 2x FM-TOM-01 back
            db.products.update_one({"tenant_id": "tenant_fresh", "sku": "FM-TOM-01"}, {"$inc": {"stock": 2}})
            db.orders.delete_many({"id": _state["order_id"]})
        db.carts.delete_many({"tenant_id": "tenant_fresh", "phone": SIM_PHONE})
        db.customers.delete_many({"tenant_id": "tenant_fresh", "phone": SIM_PHONE})
        db.conversations.delete_many({"tenant_id": "tenant_fresh", "phone": SIM_PHONE})
        db.payment_intents.delete_many({"order_id": _state["order_id"]}) if _state["order_id"] else None
        db.payment_intents.delete_many({"tenant_id": "tenant_fresh", "cart_id": {"$exists": False}, "id": _state["intent_id"]}) if _state["intent_id"] else None
        # Revert glow whatsapp creds to disconnected placeholder (best-effort)
        db.tenants.update_one({"id": "tenant_glow"}, {"$set": {"integrations.whatsapp": {"connected": False, "provider": "Meta Cloud API"}}})
        cli.close()
    except Exception as e:
        print(f"cleanup error: {e}")
