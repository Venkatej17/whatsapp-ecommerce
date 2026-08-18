"""Extended commerce services: cart engine, WhatsApp webhook + simulator,
payments (Razorpay + COD), industry template packs."""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import razorpay
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

# ---------- Encryption for per-tenant secrets ----------
_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
if not _KEY:
    # Ephemeral key for dev only; production must supply CREDENTIAL_ENCRYPTION_KEY.
    _KEY = Fernet.generate_key().decode()
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = _KEY
_fernet = Fernet(_KEY.encode())


def encrypt(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet.decrypt(value.encode()).decode()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------- Industry template packs ----------
TEMPLATE_PACKS: Dict[str, Dict[str, Any]] = {
    "Grocery": {
        "categories": ["Vegetables", "Fruits", "Dairy", "Bakery", "Staples", "Beverages"],
        "sample_products": [
            {"name": "Tomatoes", "category": "Vegetables", "price": 40, "unit": "500g", "stock": 30},
            {"name": "Onions", "category": "Vegetables", "price": 50, "unit": "1kg", "stock": 25},
            {"name": "Milk 1L", "category": "Dairy", "price": 72, "unit": "1L", "stock": 20},
            {"name": "Whole wheat bread", "category": "Bakery", "price": 55, "unit": "loaf", "stock": 15},
        ],
        "fulfilment": {"delivery_charge": 20, "free_above": 500, "prep_min": 30},
        "welcome": "👋 Welcome to {business}! Reply *shop* to browse today's fresh stock.",
    },
    "Pharmacy": {
        "categories": ["OTC medicines", "Personal care", "Baby care", "Wellness", "Devices"],
        "sample_products": [
            {"name": "Paracetamol 500mg", "category": "OTC medicines", "price": 30, "unit": "10 tabs", "stock": 40},
            {"name": "Hand sanitizer 200ml", "category": "Personal care", "price": 120, "unit": "200ml", "stock": 25},
            {"name": "Digital thermometer", "category": "Devices", "price": 249, "unit": "each", "stock": 10},
        ],
        "fulfilment": {"delivery_charge": 30, "free_above": 300, "prep_min": 20},
        "welcome": "👋 Welcome to {business}. Reply *shop* to see medicines and essentials. Prescription items are verified before dispatch.",
    },
    "Bakery": {
        "categories": ["Bread", "Cakes", "Cookies", "Pastries", "Beverages"],
        "sample_products": [
            {"name": "Fresh croissant", "category": "Pastries", "price": 65, "unit": "each", "stock": 20},
            {"name": "Chocolate cake 500g", "category": "Cakes", "price": 450, "unit": "500g", "stock": 8},
            {"name": "Sourdough loaf", "category": "Bread", "price": 180, "unit": "loaf", "stock": 12},
        ],
        "fulfilment": {"delivery_charge": 25, "free_above": 400, "prep_min": 45},
        "welcome": "🥐 Welcome to {business}! Reply *shop* to see today's fresh bakes.",
    },
    "Beauty": {
        "categories": ["Skincare", "Makeup", "Haircare", "Fragrance"],
        "sample_products": [
            {"name": "Face serum", "category": "Skincare", "price": 899, "unit": "30ml", "stock": 15},
            {"name": "Lip balm", "category": "Makeup", "price": 199, "unit": "each", "stock": 25},
        ],
        "fulfilment": {"delivery_charge": 40, "free_above": 999, "prep_min": 30},
        "welcome": "✨ Welcome to {business}! Reply *shop* to explore today's beauty picks.",
    },
}


# ---------- Pydantic ----------
class WhatsAppCredsIn(BaseModel):
    phone_number_id: str
    waba_id: str = ""
    access_token: str
    provider: str = "Meta Cloud API"


class SimulateIn(BaseModel):
    tenant_id: str
    from_phone: str
    from_name: str = "Test Customer"
    body: str


class CartItemIn(BaseModel):
    sku: str
    qty: int = 1


class FulfilmentSelectIn(BaseModel):
    method: str = Field(pattern="^(HOME_DELIVERY|STORE_PICKUP)$")
    address: str = ""


class PaymentIntentIn(BaseModel):
    cart_id: str
    provider: str = "razorpay"  # razorpay | cod


class ApplyPackIn(BaseModel):
    pack: str  # Grocery | Pharmacy | Bakery | Beauty


# ---------- Router factory ----------
def build_router(db, master_user_dep, tenant_owner_dep, audit_fn):
    """Build the extension APIRouter, given DB + auth dependencies from server.py."""
    router = APIRouter()

    # ============ CART ENGINE (tenant-scoped, per customer phone) ============
    async def _tenant(tenant_id: str):
        t = await db.tenants.find_one({"id": tenant_id})
        if not t:
            raise HTTPException(404, "Tenant not found")
        return t

    async def _get_or_create_cart(tenant_id: str, phone: str, customer_name: str = "") -> Dict[str, Any]:
        cart = await db.carts.find_one({"tenant_id": tenant_id, "phone": phone, "status": "active"}, {"_id": 0})
        if cart:
            return cart
        cart = {
            "id": new_id("cart"),
            "tenant_id": tenant_id,
            "phone": phone,
            "customer": customer_name or phone,
            "items": [],
            "fulfilment": None,
            "address": "",
            "status": "active",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        await db.carts.insert_one(dict(cart))
        return cart

    def _pickup_locations(tenant: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return the tenant's configured pickup locations (multi-store aware, backward-compatible)."""
        sp = tenant.get("fulfilment", {}).get("store_pickup", {}) or {}
        locs = sp.get("locations")
        if isinstance(locs, list) and locs:
            return locs
        single = sp.get("location") or {}
        if single.get("name") or single.get("address"):
            return [{"id": "loc_main", **single}]
        return []

    async def _recalculate(cart: Dict[str, Any]) -> Dict[str, Any]:
        """Re-validate stock+price for every item; compute totals per tenant fulfilment rules."""
        tenant = await _tenant(cart["tenant_id"])
        prods = await db.products.find({"tenant_id": cart["tenant_id"]}, {"_id": 0}).to_list(500)
        prod_by_sku = {p["sku"]: p for p in prods if p.get("sku")}

        valid_items: List[Dict[str, Any]] = []
        issues: List[str] = []
        subtotal = 0.0
        for it in cart.get("items", []):
            p = prod_by_sku.get(it["sku"])
            if not p:
                issues.append(f"{it.get('name', it['sku'])} is no longer in the catalog")
                continue
            if p.get("stock", 0) <= 0:
                issues.append(f"{p['name']} is out of stock")
                continue
            qty = min(int(it["qty"]), int(p["stock"]))
            item_total = qty * float(p["price"])
            subtotal += item_total
            valid_items.append({
                "sku": p["sku"], "name": p["name"], "qty": qty,
                "price": p["price"], "unit": p.get("unit", "each"),
                "line_total": round(item_total, 2),
            })

        delivery_charge = 0.0
        pickup_location = None
        pickup_locations = _pickup_locations(tenant)
        ful_settings = tenant.get("fulfilment", {})
        if cart.get("fulfilment") == "HOME_DELIVERY":
            d = ful_settings.get("home_delivery", {})
            if not d.get("enabled"):
                issues.append("Home delivery is not enabled for this business")
            free_above = float(d.get("free_above", 0))
            base = float(d.get("base_charge", 0))
            delivery_charge = 0.0 if (free_above and subtotal >= free_above) else base
        elif cart.get("fulfilment") == "STORE_PICKUP":
            sp = ful_settings.get("store_pickup", {})
            if not sp.get("enabled"):
                issues.append("Store pickup is not enabled for this business")
            chosen_id = cart.get("pickup_location_id")
            pickup_location = next((l for l in pickup_locations if l.get("id") == chosen_id), None) or (pickup_locations[0] if pickup_locations else None)

        # Loyalty: read customer points + apply redemption.
        customer = await db.customers.find_one({"tenant_id": cart["tenant_id"], "phone": cart["phone"]}, {"_id": 0})
        available_points = int((customer or {}).get("loyalty_points", 0))
        requested_redeem = int(cart.get("redeem_points", 0))
        max_redeem = min(available_points, int(subtotal))  # ₹1 per point, cannot exceed subtotal
        redeem = max(0, min(requested_redeem, max_redeem))
        loyalty_discount = float(redeem)

        total = round(subtotal + delivery_charge - loyalty_discount, 2)
        return {
            **cart,
            "items": valid_items,
            "subtotal": round(subtotal, 2),
            "delivery_charge": delivery_charge,
            "loyalty_discount": loyalty_discount,
            "loyalty_points_available": available_points,
            "loyalty_points_applied": redeem,
            "pickup_location": pickup_location,
            "pickup_locations": pickup_locations,
            "total": total,
            "issues": issues,
        }

    @router.post("/cart/session")
    async def cart_session(payload: Dict[str, Any], user=Depends(tenant_owner_dep)):
        cart = await _get_or_create_cart(user["tenant_id"], payload["phone"], payload.get("customer", ""))
        return await _recalculate(cart)

    @router.get("/cart/{cart_id}")
    async def cart_view(cart_id: str, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        return await _recalculate(cart)

    @router.post("/cart/{cart_id}/items")
    async def cart_add(cart_id: str, item: CartItemIn, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        prod = await db.products.find_one({"tenant_id": user["tenant_id"], "sku": item.sku}, {"_id": 0})
        if not prod:
            raise HTTPException(404, "Product not found in catalog")
        if prod.get("stock", 0) < item.qty:
            raise HTTPException(400, f"Only {prod.get('stock',0)} units available")
        items = cart.get("items", [])
        for it in items:
            if it["sku"] == item.sku:
                it["qty"] = min(it["qty"] + item.qty, prod["stock"])
                break
        else:
            items.append({"sku": prod["sku"], "name": prod["name"], "qty": item.qty, "price": prod["price"], "unit": prod.get("unit", "each")})
        await db.carts.update_one({"id": cart_id}, {"$set": {"items": items, "updated_at": now_iso()}})
        cart["items"] = items
        return await _recalculate(cart)

    @router.patch("/cart/{cart_id}/items/{sku}")
    async def cart_update(cart_id: str, sku: str, item: CartItemIn, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        items = [it for it in cart.get("items", []) if it["sku"] != sku or item.qty > 0]
        for it in items:
            if it["sku"] == sku:
                it["qty"] = item.qty
        await db.carts.update_one({"id": cart_id}, {"$set": {"items": items, "updated_at": now_iso()}})
        cart["items"] = items
        return await _recalculate(cart)

    @router.delete("/cart/{cart_id}/items/{sku}")
    async def cart_remove(cart_id: str, sku: str, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        items = [it for it in cart.get("items", []) if it["sku"] != sku]
        await db.carts.update_one({"id": cart_id}, {"$set": {"items": items, "updated_at": now_iso()}})
        cart["items"] = items
        return await _recalculate(cart)

    @router.delete("/cart/{cart_id}")
    async def cart_clear(cart_id: str, user=Depends(tenant_owner_dep)):
        await db.carts.update_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"$set": {"items": [], "updated_at": now_iso()}})
        return {"ok": True}

    @router.post("/cart/{cart_id}/fulfilment")
    async def cart_set_fulfilment(cart_id: str, payload: FulfilmentSelectIn, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        upd = {"fulfilment": payload.method, "updated_at": now_iso()}
        if payload.method == "HOME_DELIVERY":
            if not payload.address:
                raise HTTPException(400, "Delivery address is required")
            upd["address"] = payload.address
        else:
            upd["address"] = ""
        await db.carts.update_one({"id": cart_id}, {"$set": upd})
        cart.update(upd)
        return await _recalculate(cart)

    @router.post("/cart/{cart_id}/pickup-location")
    async def cart_pickup_location(cart_id: str, payload: Dict[str, Any], user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        await db.carts.update_one({"id": cart_id}, {"$set": {"pickup_location_id": payload.get("location_id"), "fulfilment": "STORE_PICKUP", "updated_at": now_iso()}})
        cart["pickup_location_id"] = payload.get("location_id")
        cart["fulfilment"] = "STORE_PICKUP"
        return await _recalculate(cart)

    @router.post("/cart/{cart_id}/redeem")
    async def cart_redeem(cart_id: str, payload: Dict[str, Any], user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        points = max(0, int(payload.get("points", 0)))
        await db.carts.update_one({"id": cart_id}, {"$set": {"redeem_points": points, "updated_at": now_iso()}})
        cart["redeem_points"] = points
        return await _recalculate(cart)

    @router.post("/cart/{cart_id}/checkout")
    async def cart_checkout(cart_id: str, user=Depends(tenant_owner_dep)):
        return await _do_checkout(cart_id, user["tenant_id"], acting_user_name=user["name"])

    async def _do_checkout(cart_id: str, tenant_id: str, acting_user_name: str = "system", origin: str = ""):
        cart = await db.carts.find_one({"id": cart_id, "tenant_id": tenant_id}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        recalculated = await _recalculate(cart)
        if not recalculated["items"]:
            raise HTTPException(400, "Cart is empty")
        if recalculated["issues"]:
            raise HTTPException(400, " · ".join(recalculated["issues"]))
        if not recalculated.get("fulfilment"):
            raise HTTPException(400, "Choose a fulfilment method before checkout")

        # Reserve stock atomically per product.
        for it in recalculated["items"]:
            res = await db.products.update_one(
                {"tenant_id": tenant_id, "sku": it["sku"], "stock": {"$gte": it["qty"]}},
                {"$inc": {"stock": -it["qty"]}},
            )
            if res.modified_count == 0:
                # roll back previously reserved items in this loop
                await db.products.update_one({"tenant_id": tenant_id, "sku": it["sku"]}, {"$inc": {"stock": 0}})
                raise HTTPException(400, f"Stock changed for {it['name']}. Please review the cart.")

        # Auto-status refresh for the modified products.
        prods_after = await db.products.find({"tenant_id": tenant_id, "sku": {"$in": [i["sku"] for i in recalculated["items"]]}}).to_list(200)
        for p in prods_after:
            s = p.get("stock", 0)
            status = "Out of stock" if s == 0 else ("Low stock" if s < 20 else "Available")
            await db.products.update_one({"_id": p["_id"]}, {"$set": {"status": status}})

        tenant = await _tenant(tenant_id)
        seq = await db.orders.count_documents({"tenant_id": tenant_id}) + 1
        order_id = f"{tenant['name'][:2].upper()}-{10000 + seq}"
        pickup_loc = recalculated.get("pickup_location") or {}
        order = {
            "id": order_id, "tenant_id": tenant_id,
            "customer": cart["customer"], "phone": cart["phone"],
            "items": [{"name": i["name"], "qty": f"{i['qty']} {i['unit']}", "price": i["line_total"]} for i in recalculated["items"]],
            "subtotal": recalculated["subtotal"], "discount": recalculated.get("loyalty_discount", 0), "tax": 0,
            "delivery_charge": recalculated["delivery_charge"], "total": recalculated["total"],
            "fulfilment": recalculated["fulfilment"],
            "payment": "COD" if cart.get("payment_choice") == "cod" else "PENDING", "status": "NEW",
            "address": cart.get("address", ""),
            "pickup_code": f"PC{uuid.uuid4().hex[:4].upper()}" if recalculated["fulfilment"] == "STORE_PICKUP" else "",
            "pickup_location_id": pickup_loc.get("id") if recalculated["fulfilment"] == "STORE_PICKUP" else "",
            "pickup_location_name": pickup_loc.get("name", "") if recalculated["fulfilment"] == "STORE_PICKUP" else "",
            "loyalty_points_applied": recalculated.get("loyalty_points_applied", 0),
            "notes": "", "assigned_to": "", "cart_id": cart_id, "source": "WhatsApp",
            "timeline": [{"status": "NEW", "at": datetime.now(timezone.utc).strftime("Today, %I:%M %p"), "by": acting_user_name}],
            "created_at": datetime.now(timezone.utc).strftime("Today, %I:%M %p"),
        }
        await db.orders.insert_one(dict(order))
        await db.carts.update_one({"id": cart_id}, {"$set": {"status": "checked_out", "order_id": order_id, "updated_at": now_iso()}})

        # Loyalty: award 1 point per ₹10 spent on new (unpaid) total, deduct redeemed points.
        earn = int(recalculated["total"] // 10)
        redeem = int(recalculated.get("loyalty_points_applied", 0))
        await db.customers.update_one(
            {"tenant_id": tenant_id, "phone": cart["phone"]},
            {"$setOnInsert": {"id": new_id("cust"), "tenant_id": tenant_id, "phone": cart["phone"], "name": cart["customer"], "tags": ["new"]},
             "$inc": {"orders_count": 1, "total_spent": recalculated["total"], "loyalty_points": earn - redeem},
             "$set": {"last_order_at": datetime.now(timezone.utc).strftime("Today, %I:%M %p")}},
            upsert=True,
        )
        order["loyalty_points_earned"] = earn
        await audit_fn(tenant_id, {"id": "whatsapp_bot", "name": acting_user_name, "role": "WHATSAPP_BOT"}, "order.created_from_cart", order_id, {"cart_id": cart_id, "phone": cart["phone"], "loyalty_delta": earn - redeem})

        # Create a Razorpay payment link for the WhatsApp customer, unless they chose cash/pay-at-store.
        payment_link = None
        if cart.get("payment_choice") != "cod":
            payment_link = await _create_payment_link(tenant, order, origin=origin)
            if payment_link:
                await db.orders.update_one({"id": order_id}, {"$set": {"payment_link": payment_link["url"], "payment_provider": payment_link["provider"], "payment_intent_id": payment_link["intent_id"]}})
                order["payment_link"] = payment_link["url"]
                order["payment_provider"] = payment_link["provider"]

        order.pop("_id", None)
        return {"order": order, "cart": recalculated, "payment_link": payment_link}

    async def _create_payment_link(tenant: Dict[str, Any], order: Dict[str, Any], origin: str = "") -> Optional[Dict[str, Any]]:
        """Return {url, provider, intent_id} for the WhatsApp customer to pay online via
        Razorpay Payment Link. Returns None if online payment isn't configured/enabled for
        this tenant — the caller then falls back to COD / pay-at-store."""
        amount_paise = int(round(order["total"] * 100))
        if amount_paise <= 0:
            return None

        payment_cfg = tenant.get("integrations", {}).get("payment", {})
        if payment_cfg and not payment_cfg.get("online_enabled", True):
            return None

        rp_key = os.environ.get("RAZORPAY_KEY_ID")
        rp_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not (rp_key and rp_secret):
            return None
        try:
            rp = razorpay.Client(auth=(rp_key, rp_secret))
            link = rp.payment_link.create({
                "amount": amount_paise, "currency": "INR",
                "accept_partial": False, "reference_id": order["id"],
                "description": f"Order {order['id']} · {tenant['name']}",
                "customer": {"name": order["customer"], "contact": order["phone"]},
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
                "notes": {"tenant_id": tenant["id"], "order_id": order["id"]},
            })
            intent = {
                "id": new_id("pi"), "tenant_id": tenant["id"], "order_id": order["id"],
                "provider": "razorpay", "amount": order["total"], "currency": "INR",
                "razorpay_link_id": link.get("id"), "status": "created", "created_at": now_iso(),
            }
            await db.payment_intents.insert_one(dict(intent))
            return {"url": link["short_url"], "provider": "razorpay", "intent_id": intent["id"]}
        except Exception:
            return None

    # ============ WHATSAPP WEBHOOK + SIMULATOR ============
    VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "commerceos-webhook-verify")

    async def _tenant_by_phone_number_id(phone_number_id: str) -> Optional[Dict[str, Any]]:
        return await db.tenants.find_one({"integrations.whatsapp.phone_number_id": phone_number_id})

    async def _log_message(tenant_id: str, phone: str, customer: str, direction: str, body: str, cart_id: Optional[str] = None, order_id: Optional[str] = None):
        conv = await db.conversations.find_one({"tenant_id": tenant_id, "phone": phone}, {"_id": 0})
        message = {"from": "customer" if direction == "in" else "bot", "body": body, "at": datetime.now(timezone.utc).strftime("Today, %I:%M %p")}
        if not conv:
            conv = {
                "id": new_id("conv"), "tenant_id": tenant_id, "customer": customer, "phone": phone,
                "linked_order_id": order_id or "", "linked_cart_id": cart_id or "",
                "status": "active", "last_at": message["at"], "messages": [message],
            }
            await db.conversations.insert_one(dict(conv))
        else:
            update: Dict[str, Any] = {"$push": {"messages": message}, "$set": {"last_at": message["at"]}}
            if cart_id:
                update["$set"]["linked_cart_id"] = cart_id
            if order_id:
                update["$set"]["linked_order_id"] = order_id
            await db.conversations.update_one({"id": conv["id"]}, update)

    async def _bot_reply(tenant: Dict[str, Any], phone: str, customer: str, body_in: str) -> str:
        """Rule-based WhatsApp shopping bot backed by the cart engine + commerce DB."""
        tenant_id = tenant["id"]
        cart = await _get_or_create_cart(tenant_id, phone, customer)
        lower = body_in.strip().lower()

        # Human handoff
        if any(k in lower for k in ["agent", "support", "help me", "talk to"]):
            await db.conversations.update_one({"tenant_id": tenant_id, "phone": phone}, {"$set": {"status": "needs_human"}})
            return "🙋 A support agent will take over shortly. You can keep typing here."

        # View cart
        if lower in ["cart", "view cart", "my cart"]:
            r = await _recalculate(cart)
            if not r["items"]:
                return "Your cart is empty. Reply *shop* to browse."
            lines = "\n".join(f"• {i['name']} × {i['qty']} — ₹{i['line_total']}" for i in r["items"])
            extras = []
            if r.get("delivery_charge"):
                extras.append(f"Delivery ₹{r['delivery_charge']}")
            if r.get("loyalty_discount"):
                extras.append(f"Points ₹{r['loyalty_discount']:.0f}")
            extra = "\n".join(extras)
            pts_line = ""
            if r.get("loyalty_points_available", 0) > 0 and not r.get("loyalty_points_applied"):
                pts_line = f"\n💎 You have *{r['loyalty_points_available']}* points. Reply *redeem <points>* to apply."
            return f"🛒 Your cart:\n{lines}\nSubtotal: ₹{r['subtotal']}\n{extra}\nTotal: ₹{r['total']}{pts_line}\nReply *delivery* or *pickup* to continue."

        # Clear cart
        if lower in ["clear", "empty", "start over"]:
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"items": [], "updated_at": now_iso()}})
            return "Cart cleared. Reply *shop* to start again."

        # Fulfilment selection
        if lower in ["delivery", "home delivery", "deliver"]:
            r = await _recalculate({**cart, "fulfilment": "HOME_DELIVERY"})
            if r["issues"] and "not enabled" in " ".join(r["issues"]):
                return "Home delivery isn't available. Reply *pickup* to collect from the store."
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"fulfilment": "HOME_DELIVERY", "updated_at": now_iso()}})
            return f"🛵 Home delivery selected. Delivery fee ₹{r['delivery_charge']}. Reply with your delivery address."

        if lower in ["pickup", "store pickup", "collect", "collect from store"]:
            sp = tenant.get("fulfilment", {}).get("store_pickup", {})
            if not sp.get("enabled"):
                return "Store pickup isn't offered. Reply *delivery* instead."
            locs = _pickup_locations(tenant)
            if len(locs) > 1:
                await db.carts.update_one({"id": cart["id"]}, {"$set": {"fulfilment": "STORE_PICKUP", "address": "", "updated_at": now_iso()}})
                lines = "\n".join(f"{i+1}. *{l.get('name','Store')}* — {l.get('address','')}" for i, l in enumerate(locs))
                return f"🏬 Choose a pickup location:\n{lines}\nReply *pickup 1*, *pickup 2*, etc."
            loc = locs[0] if locs else {}
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"fulfilment": "STORE_PICKUP", "pickup_location_id": loc.get("id"), "address": "", "updated_at": now_iso()}})
            return f"🏬 Pickup selected at *{loc.get('name','our store')}* ({loc.get('address','')}). Hours: {loc.get('hours','9 AM–9 PM')}. Reply *confirm* to place the order."

        if lower.startswith("pickup "):
            parts = lower.split()
            if len(parts) >= 2 and parts[1].isdigit():
                locs = _pickup_locations(tenant)
                idx = int(parts[1]) - 1
                if 0 <= idx < len(locs):
                    chosen = locs[idx]
                    await db.carts.update_one({"id": cart["id"]}, {"$set": {"fulfilment": "STORE_PICKUP", "pickup_location_id": chosen.get("id"), "address": "", "updated_at": now_iso()}})
                    return f"🏬 Pickup at *{chosen.get('name')}* ({chosen.get('address','')}). Hours: {chosen.get('hours','9 AM–9 PM')}. Reply *confirm* to place the order."

        if lower in ["offers", "today offers", "today's offers", "specials", "deals"]:
            offers = await db.products.find({"tenant_id": tenant_id, "is_offer": True, "stock": {"$gt": 0}}, {"_id": 0}).limit(6).to_list(6)
            if not offers:
                return "No specials today. Reply *shop* to browse the full catalog."
            lines = "\n".join(f"• *{p['name']}* — ₹{p['price']} {('· ' + p.get('offer_text','')) if p.get('offer_text') else ''} (`{p['sku']}`)" for p in offers)
            return f"🌟 Today's offers:\n{lines}\nReply *add <sku>* to grab one."

        if lower.startswith("redeem"):
            parts = lower.split()
            pts = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"redeem_points": pts, "updated_at": now_iso()}})
            r = await _recalculate({**cart, "redeem_points": pts})
            return f"💎 Applied *{r['loyalty_points_applied']}* points (₹{r['loyalty_points_applied']:.0f} off). New total: ₹{r['total']:.0f}. Reply *confirm* to place the order."

        # Address (any message when cart.fulfilment==HOME_DELIVERY and no address)
        if cart.get("fulfilment") == "HOME_DELIVERY" and not cart.get("address") and len(body_in) > 6 and lower not in ["confirm", "shop", "categories"]:
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"address": body_in, "updated_at": now_iso()}})
            r = await _recalculate({**cart, "address": body_in})
            return f"📍 Address saved. Total ₹{r['total']} (incl. ₹{r['delivery_charge']} delivery). Reply *confirm* to place the order."

        async def _proceed_to_checkout() -> str:
            try:
                result = await _do_checkout(cart["id"], tenant_id, acting_user_name="whatsapp_bot", origin=os.environ.get("PUBLIC_APP_URL", ""))
                o = result["order"]
                pay = result.get("payment_link")
                if o["fulfilment"] == "STORE_PICKUP":
                    store_name = o.get("pickup_location_name") or tenant.get("fulfilment", {}).get("store_pickup", {}).get("location", {}).get("name", "our store")
                    reply = f"✅ Order *{o['id']}* confirmed for pickup at {store_name}. Show pickup code *{o['pickup_code']}* on arrival."
                else:
                    reply = f"✅ Order *{o['id']}* confirmed. Total ₹{o['total']} · Delivery ₹{o['delivery_charge']}. We'll notify you at every step."
                if o.get("payment") == "COD":
                    reply += "\n\n💵 Pay in cash when your order arrives / when you collect it."
                elif pay:
                    reply += f"\n\n💳 Pay securely here ({pay['provider']}): {pay['url']}"
                else:
                    reply += "\n\n💳 Payment link will be sent shortly by our team."
                return reply
            except HTTPException as e:
                return f"⚠️ {e.detail}"

        # Payment method choice (only asked when the tenant has both options enabled).
        pay_cfg = tenant.get("integrations", {}).get("payment", {})
        cod_on = pay_cfg.get("cod_enabled", True)
        online_on = pay_cfg.get("online_enabled", True)
        if cod_on and lower in ["cod", "cash", "cash on delivery", "pay at store", "pay on delivery", "pay cash"]:
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"payment_choice": "cod", "updated_at": now_iso()}})
            if cart.get("awaiting_payment_choice"):
                return await _proceed_to_checkout()
            return "Got it — cash it is. Reply *confirm* to place the order."
        if online_on and lower in ["online", "pay online", "card", "upi"]:
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"payment_choice": "online", "updated_at": now_iso()}})
            if cart.get("awaiting_payment_choice"):
                return await _proceed_to_checkout()
            return "Got it — you'll get a secure payment link. Reply *confirm* to place the order."

        # Confirm → checkout
        if lower in ["confirm", "place order", "order now"]:
            if cod_on and online_on and not cart.get("payment_choice"):
                await db.carts.update_one({"id": cart["id"]}, {"$set": {"awaiting_payment_choice": True, "updated_at": now_iso()}})
                return "Before we place it — reply *pay online* or *cod* (cash on delivery / pay at store)."
            return await _proceed_to_checkout()

        # Shop / catalog
        if lower in ["hi", "hello", "hey", "start"]:
            welcome = tenant.get("welcome") or f"👋 Welcome to *{tenant['name']}*! Reply *shop* to browse."
            return welcome.replace("{business}", tenant["name"])

        if lower in ["shop", "menu", "categories", "browse"]:
            prods = await db.products.find({"tenant_id": tenant_id, "stock": {"$gt": 0}}, {"_id": 0}).limit(8).to_list(8)
            if not prods:
                return "We're restocking. Please check back soon."
            lines = "\n".join(f"• *{p['name']}* — ₹{p['price']} ({p['sku']})" for p in prods)
            return f"🛍️ Available now:\n{lines}\nReply *add <sku>* to add. Example: `add {prods[0]['sku']}`"

        # Add item: "add SKU" or "add SKU 2"
        if lower.startswith("add "):
            parts = body_in.strip().split()
            sku = parts[1] if len(parts) > 1 else ""
            qty = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            prod = await db.products.find_one({"tenant_id": tenant_id, "sku": sku}, {"_id": 0})
            if not prod:
                return f"Couldn't find *{sku}*. Reply *shop* to see available items."
            if prod["stock"] < qty:
                return f"Only {prod['stock']} units of {prod['name']} available."
            items = cart.get("items", [])
            for it in items:
                if it["sku"] == sku:
                    it["qty"] = min(it["qty"] + qty, prod["stock"])
                    break
            else:
                items.append({"sku": prod["sku"], "name": prod["name"], "qty": qty, "price": prod["price"], "unit": prod.get("unit", "each")})
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"items": items, "updated_at": now_iso()}})
            return f"✅ Added *{prod['name']}* × {qty}. Reply *cart* to review or *shop* for more."

        return "Reply *shop* to browse, *cart* to review, *delivery*/*pickup* to check out, or *agent* for help."

    @router.get("/webhooks/whatsapp")
    async def whatsapp_verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), VERIFY_TOKEN):
            ch = q.get("hub.challenge", "")
            return int(ch) if ch.isdigit() else ch
        raise HTTPException(403, "verification failed")

    def _valid_signature(raw: bytes, signature: Optional[str], app_secret: str) -> bool:
        if not signature or not signature.startswith("sha256=") or not app_secret:
            return False
        expected = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature[7:])

    @router.post("/webhooks/whatsapp")
    async def whatsapp_receive(request: Request, x_hub_signature_256: Optional[str] = Header(default=None)):
        raw = await request.body()
        app_secret = os.environ.get("META_APP_SECRET", "")
        # In dev/scaffold mode allow requests without app_secret set.
        if app_secret and not _valid_signature(raw, x_hub_signature_256, app_secret):
            raise HTTPException(401, "invalid signature")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(400, "invalid JSON") from e
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                if not phone_number_id:
                    continue
                tenant = await _tenant_by_phone_number_id(phone_number_id)
                if not tenant:
                    continue
                for msg in value.get("messages", []):
                    body = msg.get("text", {}).get("body", "") or msg.get("interactive", {}).get("body", "") or ""
                    from_phone = msg.get("from", "")
                    contact = next((c for c in value.get("contacts", []) if c.get("wa_id") == from_phone), {})
                    customer = contact.get("profile", {}).get("name", from_phone)
                    await _log_message(tenant["id"], from_phone, customer, "in", body)
                    reply = await _bot_reply(tenant, from_phone, customer, body)
                    await _log_message(tenant["id"], from_phone, customer, "out", reply)
                    # Send reply back to the customer via Meta Graph API if credentials are configured.
                    await _send_whatsapp(tenant, from_phone, reply)
                    # Browsing the catalog gets product photos, not just a text list.
                    if body.strip().lower() in ["shop", "menu", "categories", "browse"]:
                        for p in await _catalog_images(tenant["id"]):
                            caption = f"{p['name']} — ₹{p['price']}/{p.get('unit', 'each')} ({p['sku']})\nReply *add {p['sku']}* to add to cart."
                            await _send_whatsapp_image(tenant, from_phone, p["image_url"], caption)
        return {"ok": True}

    @router.post("/admin/whatsapp/simulate")
    async def whatsapp_simulate(payload: SimulateIn, user=Depends(master_user_dep)):
        tenant = await _tenant(payload.tenant_id)
        await _log_message(tenant["id"], payload.from_phone, payload.from_name, "in", payload.body)
        reply = await _bot_reply(tenant, payload.from_phone, payload.from_name, payload.body)
        await _log_message(tenant["id"], payload.from_phone, payload.from_name, "out", reply)
        conv = await db.conversations.find_one({"tenant_id": tenant["id"], "phone": payload.from_phone}, {"_id": 0})
        images = []
        if payload.body.strip().lower() in ["shop", "menu", "categories", "browse"]:
            images = await _catalog_images(tenant["id"])
        return {"reply": reply, "conversation": conv, "images": images}

    @router.post("/admin/tenants/{tenant_id}/whatsapp-creds")
    async def save_whatsapp_creds(tenant_id: str, payload: WhatsAppCredsIn, user=Depends(master_user_dep)):
        """Save the tenant's Meta Cloud API credentials (access token encrypted at rest)."""
        await db.tenants.update_one({"id": tenant_id}, {"$set": {
            "integrations.whatsapp": {
                "connected": True, "provider": payload.provider,
                "phone_number_id": payload.phone_number_id, "waba_id": payload.waba_id,
                "access_token_enc": encrypt(payload.access_token),
                "phone_number": payload.phone_number_id, "status": "Connected",
            }
        }})
        await audit_fn(tenant_id, user, "whatsapp.creds_saved", tenant_id, {"phone_number_id": payload.phone_number_id})
        return {"ok": True}

    async def _send_whatsapp(tenant: Dict[str, Any], to: str, body: str) -> Dict[str, Any]:
        wa = tenant.get("integrations", {}).get("whatsapp", {})
        if not wa.get("access_token_enc") or not wa.get("phone_number_id"):
            return {"ok": False, "reason": "WhatsApp not fully configured"}
        try:
            token = decrypt(wa["access_token_enc"])
        except Exception:
            return {"ok": False, "reason": "Invalid stored credentials"}
        url = f"https://graph.facebook.com/v23.0/{wa['phone_number_id']}/messages"
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.post(url, headers={"Authorization": f"Bearer {token}"}, json={
                "messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}
            })
        if r.status_code >= 400:
            return {"ok": False, "reason": r.text[:200]}
        return {"ok": True, "id": r.json().get("messages", [{}])[0].get("id")}

    async def _send_whatsapp_image(tenant: Dict[str, Any], to: str, image_url: str, caption: str = "") -> Dict[str, Any]:
        """Send a product photo as a WhatsApp image message (Meta requires a public https URL —
        Cloudinary links work directly). Used for catalog browsing so customers see photos, not
        just a text list."""
        wa = tenant.get("integrations", {}).get("whatsapp", {})
        if not wa.get("access_token_enc") or not wa.get("phone_number_id") or not image_url:
            return {"ok": False, "reason": "WhatsApp not configured or no image_url"}
        try:
            token = decrypt(wa["access_token_enc"])
        except Exception:
            return {"ok": False, "reason": "Invalid stored credentials"}
        graph_url = f"https://graph.facebook.com/v23.0/{wa['phone_number_id']}/messages"
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.post(graph_url, headers={"Authorization": f"Bearer {token}"}, json={
                "messaging_product": "whatsapp", "to": to, "type": "image",
                "image": {"link": image_url, "caption": caption[:1024]},
            })
        if r.status_code >= 400:
            return {"ok": False, "reason": r.text[:200]}
        return {"ok": True, "id": r.json().get("messages", [{}])[0].get("id")}

    async def _catalog_images(tenant_id: str, limit: int = 4) -> List[Dict[str, Any]]:
        """Products with a photo, for sending as WhatsApp image messages when a customer browses."""
        prods = await db.products.find(
            {"tenant_id": tenant_id, "stock": {"$gt": 0}, "image_url": {"$nin": ["", None]}},
            {"_id": 0, "sku": 1, "name": 1, "price": 1, "unit": 1, "image_url": 1},
        ).limit(limit).to_list(limit)
        return prods

    # ============ PAYMENTS (Razorpay + COD) ============
    @router.post("/workspace/payments/intent")
    async def create_payment_intent(payload: PaymentIntentIn, request: Request, user=Depends(tenant_owner_dep)):
        cart = await db.carts.find_one({"id": payload.cart_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not cart:
            raise HTTPException(404, "Cart not found")
        r = await _recalculate(cart)
        amount_paise = int(round(r["total"] * 100))
        if amount_paise <= 0:
            raise HTTPException(400, "Cart total is zero")

        if payload.provider == "cod":
            intent = {
                "id": new_id("pi"), "tenant_id": user["tenant_id"], "cart_id": payload.cart_id,
                "provider": "cod", "amount": r["total"], "currency": "INR",
                "status": "requires_action", "created_at": now_iso(),
            }
            await db.payment_intents.insert_one(dict(intent))
            return {"provider": "cod", "amount": r["total"], "intent_id": intent["id"]}

        # default / explicit: razorpay
        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not (key_id and key_secret):
            raise HTTPException(400, "Razorpay is not configured (add RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET). Use provider=cod for now.")
        rp = razorpay.Client(auth=(key_id, key_secret))
        order = rp.order.create({"amount": amount_paise, "currency": "INR", "payment_capture": 1})
        intent = {
            "id": new_id("pi"), "tenant_id": user["tenant_id"], "cart_id": payload.cart_id,
            "provider": "razorpay", "amount": r["total"], "currency": "INR",
            "razorpay_order_id": order["id"], "status": "created", "created_at": now_iso(),
        }
        await db.payment_intents.insert_one(dict(intent))
        return {"provider": "razorpay", "key_id": key_id, "order": order, "intent_id": intent["id"]}

    @router.get("/workspace/payments/status/{intent_id}")
    async def payment_status(intent_id: str, user=Depends(tenant_owner_dep)):
        intent = await db.payment_intents.find_one({"id": intent_id, "tenant_id": user["tenant_id"]}, {"_id": 0})
        if not intent:
            raise HTTPException(404, "Payment intent not found")
        if intent["provider"] == "razorpay" and (intent.get("razorpay_order_id") or intent.get("razorpay_link_id")):
            key_id = os.environ.get("RAZORPAY_KEY_ID")
            key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
            if not (key_id and key_secret):
                return intent
            rp = razorpay.Client(auth=(key_id, key_secret))
            new_status = intent["status"]
            if intent.get("razorpay_link_id"):
                link = rp.payment_link.fetch(intent["razorpay_link_id"])
                new_status = "paid" if link.get("status") == "paid" else intent["status"]
            elif intent.get("razorpay_order_id"):
                order = rp.order.fetch(intent["razorpay_order_id"])
                new_status = "paid" if order.get("status") == "paid" else intent["status"]
            await db.payment_intents.update_one({"id": intent_id}, {"$set": {"status": new_status}})
            if new_status == "paid":
                cart = await db.carts.find_one({"id": intent["cart_id"]})
                if cart and cart.get("order_id"):
                    await db.orders.update_one({"id": cart["order_id"]}, {"$set": {"payment": "PAID"}})
            return {**intent, "status": new_status}
        return intent

    @router.post("/webhooks/razorpay")
    async def razorpay_webhook(request: Request):
        raw = await request.body()
        signature = request.headers.get("X-Razorpay-Signature", "")
        secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        if secret:
            expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise HTTPException(401, "invalid signature")
        payload = json.loads(raw or b"{}")
        event = payload.get("event", "")
        if event == "payment.captured":
            payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
            order_id = payment.get("order_id")
            intent = await db.payment_intents.find_one({"razorpay_order_id": order_id})
            if intent:
                await db.payment_intents.update_one({"id": intent["id"]}, {"$set": {"status": "paid"}})
                cart = await db.carts.find_one({"id": intent["cart_id"]})
                if cart and cart.get("order_id"):
                    await db.orders.update_one({"id": cart["order_id"]}, {"$set": {"payment": "PAID"}})
        return {"ok": True}

    # ============ INDUSTRY TEMPLATE PACKS ============
    @router.get("/admin/template-packs")
    async def list_packs(user=Depends(master_user_dep)):
        return [{"name": k, "categories": v["categories"], "products": len(v["sample_products"]), "welcome": v["welcome"]} for k, v in TEMPLATE_PACKS.items()]

    @router.get("/admin/tenants/{tenant_id}/onboarding-doc")
    async def onboarding_doc(tenant_id: str, user=Depends(master_user_dep)):
        """Auto-generate a one-page onboarding playbook the client can be handed on day one."""
        tenant = await _tenant(tenant_id)
        owner = await db.users.find_one({"tenant_id": tenant_id, "role": "TENANT_OWNER"}, {"_id": 0, "password_hash": 0})
        b = tenant.get("business", {})
        f = tenant.get("fulfilment", {})
        wa = tenant.get("integrations", {}).get("whatsapp", {})
        pay = tenant.get("integrations", {}).get("payment", {})
        onb = tenant.get("onboarding", {})
        products = await db.products.find({"tenant_id": tenant_id}, {"_id": 0}).limit(6).to_list(6)
        completed = sum(1 for v in onb.values() if v)
        total = max(len(onb), 1)

        md = f"""# {tenant['name']} — Welcome to Commerce OS

**Category:** {tenant['category']}  ·  **Status:** {tenant.get('status')}  ·  **Readiness:** {round(completed/total*100)}%

## 1. Your workspace
- **Owner login:** `{owner['email'] if owner else '—'}`
- **Sign-in URL:** {os.environ.get('PUBLIC_APP_URL', 'https://your-commerceos-url')}
- **Business phone:** {b.get('phone') or '—'}  ·  **Business email:** {b.get('email') or '—'}
- **Location:** {b.get('city') or '—'}, {b.get('state') or '—'} · {b.get('pincode') or '—'}

## 2. WhatsApp channel
- **Status:** {'Connected' if wa.get('connected') else 'Not connected'}
- **Provider:** {wa.get('provider','Meta Cloud API')}
- **Phone number ID:** `{wa.get('phone_number_id','—')}`
- **Customer greeting:** {tenant.get('welcome') or 'Default welcome'}

Once connected, your customers can just message this number to shop, view cart, and pay.

## 3. Fulfilment rules
- **Home delivery:** {'Enabled' if f.get('home_delivery',{}).get('enabled') else 'Disabled'} · ₹{f.get('home_delivery',{}).get('base_charge',0)} · Free above ₹{f.get('home_delivery',{}).get('free_above',0)}
- **Store pickup:** {'Enabled' if f.get('store_pickup',{}).get('enabled') else 'Disabled'} · Location: {f.get('store_pickup',{}).get('location',{}).get('name','—')} · Hours {f.get('store_pickup',{}).get('location',{}).get('hours','—')}

## 4. Payments
- **Provider:** {pay.get('provider','Razorpay')}  ·  **Modes:** {'Online ✓ ' if pay.get('online_enabled') else ''}{'UPI ✓ ' if pay.get('upi_enabled') else ''}{'COD ✓' if pay.get('cod_enabled') else ''}
- Payment links are sent inside WhatsApp automatically after every order confirmation.

## 5. Starter catalog ({len(products)} items)
""" + "\n".join(f"- **{p['name']}** — ₹{p['price']} ({p.get('sku','')})" for p in products) + f"""

## 6. Daily operations
1. Open the workspace every morning and glance at *Today's orders*.
2. Move each order through **New → Picking → Packing → Ready** on the Fulfilment board.
3. Update stock from the **Inventory** page — the WhatsApp bot auto-refuses out-of-stock items.
4. WhatsApp customers get automatic notifications at every stage.

## 7. Need help?
- **Support inside dashboard:** Click *Sign out* → Support in the login screen.
- **Platform status:** All-systems indicator in the top bar.
"""
        return {"markdown": md, "tenant_name": tenant["name"]}

    @router.post("/admin/tenants/{tenant_id}/apply-pack")
    async def apply_pack(tenant_id: str, payload: ApplyPackIn, user=Depends(master_user_dep)):
        pack = TEMPLATE_PACKS.get(payload.pack)
        if not pack:
            raise HTTPException(404, "Unknown template pack")
        # Seed products with tenant-specific SKU prefix.
        prefix = "".join(w[0].upper() for w in payload.pack.split())[:3]
        new_products = []
        for i, p in enumerate(pack["sample_products"]):
            sku = f"{prefix}-{i+1:03d}"
            existing = await db.products.find_one({"tenant_id": tenant_id, "sku": sku})
            if existing:
                continue
            doc = {
                "id": new_id("prod"), "tenant_id": tenant_id, "sku": sku,
                "name": p["name"], "category": p["category"], "price": p["price"],
                "unit": p["unit"], "stock": p["stock"], "description": "",
                "status": "Available" if p["stock"] > 20 else ("Low stock" if p["stock"] > 0 else "Out of stock"),
            }
            await db.products.insert_one(dict(doc))
            new_products.append(sku)
        # Apply fulfilment defaults + welcome message.
        f = pack["fulfilment"]
        tenant = await db.tenants.find_one({"id": tenant_id})
        current_ful = tenant.get("fulfilment", {}) if tenant else {}
        current_ful.setdefault("home_delivery", {}).update({"enabled": True, "base_charge": f["delivery_charge"], "free_above": f["free_above"]})
        current_ful.setdefault("store_pickup", {}).update({"enabled": True, "preparation_minutes": f["prep_min"]})
        await db.tenants.update_one({"id": tenant_id}, {"$set": {
            "fulfilment": current_ful,
            "welcome": pack["welcome"],
            "onboarding.fulfilment_configured": True,
            "onboarding.catalog_connected": True,
        }})
        await audit_fn(tenant_id, user, "template_pack.applied", tenant_id, {"pack": payload.pack, "products": len(new_products)})
        return {"ok": True, "pack": payload.pack, "products_added": new_products}

    return router
