"""Tests for commerce_ext: cart engine, WhatsApp webhook+simulator, payments, template packs."""
import os
import uuid
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@commerceos.com", "password": "Admin123!"}
OWNER_FRESH = {"email": "owner@freshmart.com", "password": "Owner123!"}
OWNER_GLOW = {"email": "owner@glowcosmetics.com", "password": "Owner123!"}
OWNER_ABC = {"email": "owner@abcpharmacy.com", "password": "Owner123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds)
    assert r.status_code == 200, r.text
    return s


# ---------------- WhatsApp webhook verify ----------------
def test_whatsapp_verify_valid_token_returns_challenge():
    r = requests.get(
        f"{BASE_URL}/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "commerceos-webhook-verify",
            "hub.challenge": "123456",
        },
    )
    assert r.status_code == 200
    # returns int (echoed challenge)
    assert r.text.strip() == "123456"


def test_whatsapp_verify_wrong_token_returns_403():
    r = requests.get(
        f"{BASE_URL}/api/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert r.status_code == 403


# ---------------- WhatsApp simulator ----------------
_SIM_PHONE = f"9198000{uuid.uuid4().hex[:5]}"


def test_whatsapp_simulator_hi_then_shop_then_add_pickup_confirm():
    admin = _login(ADMIN)

    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": _SIM_PHONE,
                         "from_name": "TEST Sim Cust", "body": "hi"})
    assert r.status_code == 200, r.text
    reply_hi = r.json()["reply"].lower()
    assert "welcome" in reply_hi or "fresh mart" in reply_hi

    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": _SIM_PHONE,
                         "from_name": "TEST Sim Cust", "body": "shop"})
    assert r.status_code == 200
    assert "FM-" in r.json()["reply"]

    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": _SIM_PHONE,
                         "from_name": "TEST Sim Cust", "body": "add FM-TOM-01 2"})
    assert r.status_code == 200
    assert "added" in r.json()["reply"].lower()

    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": _SIM_PHONE,
                         "from_name": "TEST Sim Cust", "body": "pickup"})
    assert r.status_code == 200
    assert "pickup" in r.json()["reply"].lower()

    r = admin.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": _SIM_PHONE,
                         "from_name": "TEST Sim Cust", "body": "confirm"})
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "confirmed" in reply.lower(), reply

    # Verify order shows in owner's NEW queue with source=WhatsApp
    owner = _login(OWNER_FRESH)
    q = owner.get(f"{BASE_URL}/api/workspace/fulfilment/queues")
    assert q.status_code == 200
    data = q.json()
    # Structure could be dict of columns
    dumped = str(data)
    assert _SIM_PHONE in dumped or "TEST Sim Cust" in dumped, f"New order not found in queues: {dumped[:400]}"
    assert "WhatsApp" in dumped


# ---------------- Cart engine ----------------
def test_cart_engine_full_flow_home_delivery_reserves_stock():
    owner = _login(OWNER_FRESH)

    # baseline stock for FM-ONI-01 (stock=18)
    prods = owner.get(f"{BASE_URL}/api/workspace/products").json()
    onion = next(p for p in prods if p["sku"] == "FM-ONI-01")
    baseline_stock = onion["stock"]

    phone = f"9198111{uuid.uuid4().hex[:5]}"
    r = owner.post(f"{BASE_URL}/api/cart/session", json={"phone": phone, "customer": "TEST Cart Cust"})
    assert r.status_code == 200, r.text
    cart_id = r.json()["id"]

    # Add 2 x FM-ONI-01 (50 each = 100 subtotal, < 500 → delivery ₹20)
    r = owner.post(f"{BASE_URL}/api/cart/{cart_id}/items", json={"sku": "FM-ONI-01", "qty": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subtotal"] == 100.0

    # Select HOME_DELIVERY
    r = owner.post(f"{BASE_URL}/api/cart/{cart_id}/fulfilment",
                   json={"method": "HOME_DELIVERY", "address": "TEST addr 42 Somewhere"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["delivery_charge"] == 20.0
    assert body["total"] == 120.0

    # Checkout
    r = owner.post(f"{BASE_URL}/api/cart/{cart_id}/checkout")
    assert r.status_code == 200, r.text
    result = r.json()
    order = result["order"]
    assert order["source"] == "WhatsApp"
    assert order["total"] == 120.0
    assert order["delivery_charge"] == 20.0

    # Verify stock decreased by 2
    prods2 = owner.get(f"{BASE_URL}/api/workspace/products").json()
    onion2 = next(p for p in prods2 if p["sku"] == "FM-ONI-01")
    assert onion2["stock"] == baseline_stock - 2, f"expected {baseline_stock-2}, got {onion2['stock']}"

    # Customer upsert
    custs = owner.get(f"{BASE_URL}/api/workspace/customers").json()
    assert any(c.get("phone") == phone for c in custs)


def test_cart_free_delivery_above_threshold():
    owner = _login(OWNER_FRESH)
    phone = f"9198222{uuid.uuid4().hex[:5]}"
    r = owner.post(f"{BASE_URL}/api/cart/session", json={"phone": phone, "customer": "TEST Big Cust"})
    cart_id = r.json()["id"]
    # 2 x FM-MAN-01 (380 each = 760 > 500 → free delivery)
    r = owner.post(f"{BASE_URL}/api/cart/{cart_id}/items", json={"sku": "FM-MAN-01", "qty": 2})
    assert r.status_code == 200
    r = owner.post(f"{BASE_URL}/api/cart/{cart_id}/fulfilment",
                   json={"method": "HOME_DELIVERY", "address": "TEST addr"})
    body = r.json()
    assert body["delivery_charge"] == 0.0
    assert body["total"] == 760.0


# ---------------- Tenant isolation on cart ----------------
def test_cart_tenant_isolation():
    fresh = _login(OWNER_FRESH)
    phone = f"9198333{uuid.uuid4().hex[:5]}"
    r = fresh.post(f"{BASE_URL}/api/cart/session", json={"phone": phone, "customer": "TEST Iso"})
    cart_id = r.json()["id"]
    glow = _login(OWNER_GLOW)
    r = glow.get(f"{BASE_URL}/api/cart/{cart_id}")
    assert r.status_code == 404


# ---------------- Payments ----------------
def test_payment_intent_stripe():
    owner = _login(OWNER_FRESH)
    phone = f"9198444{uuid.uuid4().hex[:5]}"
    cart_id = owner.post(f"{BASE_URL}/api/cart/session",
                         json={"phone": phone, "customer": "TEST Pay"}).json()["id"]
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/items", json={"sku": "FM-ONI-01", "qty": 1})
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/fulfilment",
               json={"method": "STORE_PICKUP", "address": ""})
    r = owner.post(f"{BASE_URL}/api/workspace/payments/intent",
                   json={"cart_id": cart_id, "provider": "stripe"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "stripe"
    assert body.get("url", "").startswith("http")
    assert body.get("session_id")
    assert body.get("intent_id")


def test_payment_intent_razorpay_not_configured():
    owner = _login(OWNER_FRESH)
    phone = f"9198555{uuid.uuid4().hex[:5]}"
    cart_id = owner.post(f"{BASE_URL}/api/cart/session",
                         json={"phone": phone, "customer": "TEST RP"}).json()["id"]
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/items", json={"sku": "FM-ONI-01", "qty": 1})
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/fulfilment",
               json={"method": "STORE_PICKUP", "address": ""})
    r = owner.post(f"{BASE_URL}/api/workspace/payments/intent",
                   json={"cart_id": cart_id, "provider": "razorpay"})
    assert r.status_code == 400
    assert "not configured" in r.text.lower()


def test_payment_intent_cod():
    owner = _login(OWNER_FRESH)
    phone = f"9198666{uuid.uuid4().hex[:5]}"
    cart_id = owner.post(f"{BASE_URL}/api/cart/session",
                         json={"phone": phone, "customer": "TEST COD"}).json()["id"]
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/items", json={"sku": "FM-ONI-01", "qty": 1})
    owner.post(f"{BASE_URL}/api/cart/{cart_id}/fulfilment",
               json={"method": "STORE_PICKUP", "address": ""})
    r = owner.post(f"{BASE_URL}/api/workspace/payments/intent",
                   json={"cart_id": cart_id, "provider": "cod"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "cod"
    assert body["amount"] == 50.0
    assert body.get("intent_id")


# ---------------- Template packs ----------------
def test_template_packs_list_has_4():
    admin = _login(ADMIN)
    r = admin.get(f"{BASE_URL}/api/admin/template-packs")
    assert r.status_code == 200
    packs = r.json()
    names = {p["name"] for p in packs}
    assert names == {"Grocery", "Pharmacy", "Bakery", "Beauty"}


def test_apply_bakery_pack_to_abc_pharmacy_seeds_products():
    admin = _login(ADMIN)
    r = admin.post(f"{BASE_URL}/api/admin/tenants/tenant_abc/apply-pack",
                   json={"pack": "Bakery"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pack"] == "Bakery"
    # Verify products visible in abcpharmacy owner workspace
    owner = _login(OWNER_ABC)
    prods = owner.get(f"{BASE_URL}/api/workspace/products").json()
    skus = {p["sku"] for p in prods}
    # Bakery prefix "B" (single word) — 3 sample products BAK-001..003? Check prefix
    # commerce_ext: prefix = first letter of each word of pack name → "B"
    bakery_skus = {s for s in skus if s.startswith("B-") or s.startswith("BAK")}
    # After first call it may already have been applied; ensure at least 3 bakery SKUs
    assert len(bakery_skus) >= 3, f"Bakery skus: {bakery_skus}, all: {skus}"


# ---------------- Role isolation on new endpoints ----------------
def test_tenant_owner_cannot_call_admin_simulate():
    owner = _login(OWNER_FRESH)
    r = owner.post(f"{BASE_URL}/api/admin/whatsapp/simulate",
                   json={"tenant_id": "tenant_fresh", "from_phone": "919800000000", "body": "hi"})
    assert r.status_code == 403


def test_tenant_owner_cannot_apply_pack():
    owner = _login(OWNER_FRESH)
    r = owner.post(f"{BASE_URL}/api/admin/tenants/tenant_fresh/apply-pack",
                   json={"pack": "Grocery"})
    assert r.status_code == 403


def test_master_admin_cannot_call_cart():
    admin = _login(ADMIN)
    r = admin.post(f"{BASE_URL}/api/cart/session", json={"phone": "919800000000", "customer": "x"})
    assert r.status_code == 403


def test_master_admin_cannot_call_payments():
    admin = _login(ADMIN)
    r = admin.post(f"{BASE_URL}/api/workspace/payments/intent",
                   json={"cart_id": "cart_x", "provider": "stripe"})
    assert r.status_code == 403
