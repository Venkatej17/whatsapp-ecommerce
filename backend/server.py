from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pydantic import BaseModel, Field, EmailStr
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import os, uuid, bcrypt, jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="Commerce OS API")
api = APIRouter(prefix="/api")
JWT_ALGORITHM = "HS256"


# ---------- Utilities ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str, token_type: str, minutes: int) -> str:
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes), "type": token_type},
        os.environ["JWT_SECRET"],
        algorithm=JWT_ALGORITHM,
    )


async def current_user(request: Request):
    token = request.cookies.get("access_token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(401, "User not found")
        return user
    except jwt.PyJWTError as error:
        raise HTTPException(401, "Invalid or expired session") from error


async def master_user(user=Depends(current_user)):
    if user.get("role") != "MASTER_ADMIN":
        raise HTTPException(403, "Master Admin access required")
    return user


async def tenant_owner(user=Depends(current_user)):
    if user.get("role") != "TENANT_OWNER":
        raise HTTPException(403, "Client workspace access required")
    return user


async def audit(tenant_id: Optional[str], actor: Dict[str, Any], action: str, target: str, meta: Optional[Dict] = None):
    await db.audit_logs.insert_one({
        "id": new_id("log"),
        "tenant_id": tenant_id,
        "actor_id": actor.get("id"),
        "actor_name": actor.get("name"),
        "actor_role": actor.get("role"),
        "action": action,
        "target": target,
        "meta": meta or {},
        "at": now_iso(),
    })


# ---------- Pydantic models ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProductIn(BaseModel):
    name: str
    category: str
    price: float
    stock: int = 0
    sku: str = ""
    unit: str = "each"
    description: str = ""
    status: Optional[str] = None
    image_url: str = ""


class ProductPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    sku: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_offer: Optional[bool] = None
    offer_text: Optional[str] = None
    image_url: Optional[str] = None


class OrderStatusIn(BaseModel):
    status: str
    note: Optional[str] = None


class OrderNoteIn(BaseModel):
    note: str
    kind: str = "internal"  # internal | customer


class OrderAssignIn(BaseModel):
    staff_name: str


class ManualOrderIn(BaseModel):
    customer: str
    phone: str
    items: List[Dict[str, Any]]
    fulfilment: str = "HOME_DELIVERY"
    payment: str = "PENDING"
    address: str = ""


class ClientCreateIn(BaseModel):
    business_name: str
    category: str
    description: str = ""
    phone: str = ""
    email: EmailStr
    city: str = ""
    state: str = ""
    pincode: str = ""
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"
    owner_name: str
    owner_email: EmailStr
    owner_password: str = "Owner123!"


class TenantPatchIn(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


class WhatsAppConfigIn(BaseModel):
    phone_number: str
    business_account_id: str = ""
    provider: str = "Meta Cloud API"


class CatalogConfigIn(BaseModel):
    source: str = "Internal"
    external_id: str = ""


class PaymentConfigIn(BaseModel):
    provider: str = "Razorpay"
    cod_enabled: bool = True
    upi_enabled: bool = True
    online_enabled: bool = True


class FulfilmentConfigIn(BaseModel):
    delivery_enabled: bool = True
    delivery_charge: float = 20
    delivery_free_above: float = 500
    min_order: float = 0
    delivery_zones: List[str] = []
    pickup_enabled: bool = True
    pickup_location_name: str = ""
    pickup_address: str = ""
    pickup_hours: str = "9 AM – 9 PM"
    preparation_minutes: int = 30
    pickup_locations: Optional[List[Dict[str, Any]]] = None  # multi-store: [{id,name,address,hours}]


class TemplateIn(BaseModel):
    name: str
    category: str
    body: str
    trigger: str = "manual"


class AutomationIn(BaseModel):
    name: str
    event: str
    action: str
    enabled: bool = True


# ---------- Seed data ----------
DEFAULT_TEMPLATES = [
    {"id": "tpl_welcome", "name": "Welcome message", "category": "welcome", "trigger": "customer_first_message", "body": "👋 Welcome to {business}! Tap Shop Now to browse."},
    {"id": "tpl_order_confirmed", "name": "Order confirmation", "category": "order", "trigger": "order_created", "body": "🎉 Your order {order_id} is confirmed. Total {total}."},
    {"id": "tpl_ready_pickup", "name": "Ready for pickup", "category": "pickup", "trigger": "status_ready_for_pickup", "body": "✅ Your order {order_id} is ready to collect at {store}."},
    {"id": "tpl_out_delivery", "name": "Out for delivery", "category": "delivery", "trigger": "status_out_for_delivery", "body": "🛵 Your order {order_id} is on the way!"},
    {"id": "tpl_delivered", "name": "Delivered", "category": "delivery", "trigger": "status_delivered", "body": "✅ Order {order_id} delivered. Thank you!"},
    {"id": "tpl_abandon", "name": "Abandoned cart", "category": "cart", "trigger": "cart_abandoned", "body": "👋 You still have items in your cart at {business}."},
]

DEFAULT_AUTOMATIONS = [
    {"name": "Auto-notify: order confirmed", "event": "order_created", "action": "send_template:tpl_order_confirmed"},
    {"name": "Auto-notify: ready for pickup", "event": "status_ready_for_pickup", "action": "send_template:tpl_ready_pickup"},
    {"name": "Auto-notify: out for delivery", "event": "status_out_for_delivery", "action": "send_template:tpl_out_delivery"},
    {"name": "Abandoned cart reminder (2h)", "event": "cart_abandoned", "action": "send_template:tpl_abandon"},
]


def default_tenant_config() -> Dict[str, Any]:
    return {
        "business": {"description": "", "phone": "", "email": "", "address": "", "city": "", "state": "", "pincode": "", "currency": "INR", "timezone": "Asia/Kolkata", "gst": "", "website": ""},
        "onboarding": {"business_created": True, "owner_login_created": True, "whatsapp_connected": False, "catalog_connected": False, "templates_configured": False, "automations_configured": False, "payment_configured": False, "fulfilment_configured": False, "test_order_completed": False, "ready_to_go_live": False},
        "integrations": {
            "whatsapp": {"connected": False, "phone_number": "", "business_account_id": "", "provider": "Meta Cloud API", "status": "Not connected"},
            "catalog": {"connected": False, "source": "Internal", "last_synced": None},
            "payment": {"provider": "Razorpay", "mode": "test", "cod_enabled": True, "upi_enabled": True, "online_enabled": True, "configured": False},
        },
        "fulfilment": {
            "home_delivery": {"enabled": True, "base_charge": 20, "free_above": 500, "min_order": 0, "zones": []},
            "store_pickup": {"enabled": True, "location": {"name": "", "address": "", "hours": "9 AM – 9 PM"}, "preparation_minutes": 30},
        },
        "templates": [t["id"] for t in DEFAULT_TEMPLATES],
        "automations": [],
    }


async def ensure_seed():
    await db.users.create_index("email", unique=True)
    await db.tenants.create_index("id", unique=True)
    await db.products.create_index([("tenant_id", 1), ("id", 1)])
    await db.orders.create_index([("tenant_id", 1), ("id", 1)])
    await db.customers.create_index([("tenant_id", 1), ("phone", 1)])
    await db.audit_logs.create_index("at")

    if await db.templates.count_documents({}) == 0:
        await db.templates.insert_many(DEFAULT_TEMPLATES)

    # Demo tenants/products/orders/conversations are only for exploring the product before
    # you have real clients. Set SEED_DEMO_DATA=false once you're ready to onboard a real
    # tenant on this database, so demo data doesn't sit alongside real client data.
    if os.environ.get("SEED_DEMO_DATA", "true").lower() == "true":
        if await db.tenants.count_documents({}) == 0:
            fresh = default_tenant_config()
            fresh["business"].update({"description": "Fresh groceries & daily essentials", "phone": "+91 44 4400 1200", "email": "hello@freshmart.com", "city": "Chennai", "state": "TN", "pincode": "600001"})
            fresh["integrations"]["whatsapp"] = {"connected": True, "phone_number": "+91 91234 56780", "business_account_id": "waba_fresh_001", "provider": "Meta Cloud API", "status": "Connected"}
            fresh["integrations"]["catalog"] = {"connected": True, "source": "Internal", "last_synced": now_iso()}
            fresh["integrations"]["payment"]["configured"] = True
            fresh["fulfilment"]["store_pickup"]["location"] = {"name": "Fresh Mart T. Nagar", "address": "123 Main Road, Chennai 600017", "hours": "9 AM – 9 PM"}
            fresh["automations"] = [{"id": new_id("aut"), **a, "enabled": True} for a in DEFAULT_AUTOMATIONS]
            fresh["onboarding"].update({"whatsapp_connected": True, "catalog_connected": True, "templates_configured": True, "automations_configured": True, "payment_configured": True, "fulfilment_configured": True, "test_order_completed": True, "ready_to_go_live": True})

            glow = default_tenant_config()
            glow["business"].update({"description": "Premium skincare & cosmetics", "phone": "+91 22 5511 4400", "email": "hello@glowcosmetics.com", "city": "Mumbai", "state": "MH", "pincode": "400001"})
            glow["integrations"]["whatsapp"] = {"connected": True, "phone_number": "+91 91234 56781", "business_account_id": "waba_glow_001", "provider": "Meta Cloud API", "status": "Connected"}
            glow["integrations"]["catalog"] = {"connected": True, "source": "Internal", "last_synced": now_iso()}
            glow["integrations"]["payment"]["configured"] = True
            glow["onboarding"].update({"whatsapp_connected": True, "catalog_connected": True, "templates_configured": True, "payment_configured": True, "fulfilment_configured": True})

            abc = default_tenant_config()
            abc["business"].update({"description": "Neighbourhood pharmacy", "phone": "+91 80 4400 8800", "email": "care@abcpharmacy.com", "city": "Bengaluru", "state": "KA", "pincode": "560001"})

            await db.tenants.insert_many([
                {"id": "tenant_fresh", "name": "Fresh Mart", "category": "Grocery", "status": "Active", "orders": 128, "revenue": 18420, "health": 94, **fresh},
                {"id": "tenant_glow", "name": "Glow Cosmetics", "category": "Beauty", "status": "Active", "orders": 86, "revenue": 12680, "health": 82, **glow},
                {"id": "tenant_abc", "name": "ABC Pharmacy", "category": "Pharmacy", "status": "Onboarding", "orders": 0, "revenue": 0, "health": 38, **abc},
            ])

        if await db.products.count_documents({}) == 0:
            await db.products.insert_many([
                {"id": "prod_1", "tenant_id": "tenant_fresh", "name": "Organic Tomatoes", "category": "Vegetables", "price": 40, "stock": 52, "sku": "FM-TOM-01", "unit": "500g", "description": "Fresh farm tomatoes", "status": "Available"},
                {"id": "prod_2", "tenant_id": "tenant_fresh", "name": "Red Onions", "category": "Vegetables", "price": 50, "stock": 18, "sku": "FM-ONI-01", "unit": "1kg", "description": "", "status": "Low stock"},
                {"id": "prod_3", "tenant_id": "tenant_fresh", "name": "A2 Milk 1L", "category": "Dairy", "price": 72, "stock": 0, "sku": "FM-MIL-01", "unit": "1L", "description": "", "status": "Out of stock"},
                {"id": "prod_4", "tenant_id": "tenant_fresh", "name": "Baby Spinach", "category": "Greens", "price": 35, "stock": 31, "sku": "FM-SPN-01", "unit": "bunch", "description": "", "status": "Available"},
                {"id": "prod_5", "tenant_id": "tenant_fresh", "name": "Potatoes", "category": "Vegetables", "price": 30, "stock": 44, "sku": "FM-POT-01", "unit": "1kg", "description": "", "status": "Available"},
                {"id": "prod_6", "tenant_id": "tenant_fresh", "name": "Alphonso Mangoes", "category": "Fruits", "price": 380, "stock": 12, "sku": "FM-MAN-01", "unit": "1kg", "description": "Seasonal", "status": "Low stock"},
                {"id": "prod_7", "tenant_id": "tenant_glow", "name": "Vitamin C Serum", "category": "Skincare", "price": 899, "stock": 23, "sku": "GC-VCS-01", "unit": "30ml", "description": "", "status": "Available"},
                {"id": "prod_8", "tenant_id": "tenant_glow", "name": "Hydrating Cream", "category": "Skincare", "price": 549, "stock": 45, "sku": "GC-HYC-01", "unit": "50g", "description": "", "status": "Available"},
            ])

        if await db.orders.count_documents({}) == 0:
            await db.orders.insert_many([
                {"id": "FM-10245", "tenant_id": "tenant_fresh", "customer": "Rahul Mehta", "phone": "+91 98765 43210", "items": [{"name": "Organic Tomatoes", "qty": "2 kg", "price": 80}, {"name": "Red Onions", "qty": "1 kg", "price": 50}, {"name": "Potatoes", "qty": "2 kg", "price": 60}], "subtotal": 190, "discount": 0, "tax": 0, "delivery_charge": 0, "total": 190, "fulfilment": "STORE_PICKUP", "payment": "PAID", "status": "READY_FOR_PICKUP", "address": "", "pickup_code": "FM4521", "notes": "", "timeline": [{"status": "NEW", "at": "Today, 10:42 AM", "by": "system"}, {"status": "PICKING", "at": "Today, 10:50 AM", "by": "Ravi"}, {"status": "PACKING", "at": "Today, 11:05 AM", "by": "Ravi"}, {"status": "READY_FOR_PICKUP", "at": "Today, 11:15 AM", "by": "Ravi"}], "assigned_to": "Ravi", "created_at": "Today, 10:42 AM"},
                {"id": "FM-10244", "tenant_id": "tenant_fresh", "customer": "Priya Shah", "phone": "+91 98420 11032", "items": [{"name": "A2 Milk 1L", "qty": "2", "price": 144}], "subtotal": 144, "discount": 0, "tax": 0, "delivery_charge": 20, "total": 164, "fulfilment": "HOME_DELIVERY", "payment": "PAID", "status": "OUT_FOR_DELIVERY", "address": "12 Marina Lane, Chennai 600004", "pickup_code": "", "notes": "Ring twice", "timeline": [{"status": "NEW", "at": "Today, 10:15 AM", "by": "system"}, {"status": "PACKING", "at": "Today, 10:22 AM", "by": "Ravi"}, {"status": "OUT_FOR_DELIVERY", "at": "Today, 10:40 AM", "by": "Suresh"}], "assigned_to": "Suresh", "created_at": "Today, 10:15 AM"},
                {"id": "FM-10243", "tenant_id": "tenant_fresh", "customer": "Arjun Rao", "phone": "+91 99001 32211", "items": [{"name": "Baby Spinach", "qty": "3", "price": 105}], "subtotal": 105, "discount": 0, "tax": 0, "delivery_charge": 20, "total": 125, "fulfilment": "HOME_DELIVERY", "payment": "PENDING", "status": "NEW", "address": "45 Anna Nagar, Chennai 600040", "pickup_code": "", "notes": "", "timeline": [{"status": "NEW", "at": "Today, 09:58 AM", "by": "system"}], "assigned_to": "", "created_at": "Today, 09:58 AM"},
                {"id": "FM-10242", "tenant_id": "tenant_fresh", "customer": "Neha Iyer", "phone": "+91 98880 44022", "items": [{"name": "Organic Tomatoes", "qty": "1 kg", "price": 40}], "subtotal": 40, "discount": 0, "tax": 0, "delivery_charge": 0, "total": 40, "fulfilment": "STORE_PICKUP", "payment": "PAID", "status": "COMPLETED", "address": "", "pickup_code": "FM4487", "notes": "", "timeline": [{"status": "COMPLETED", "at": "Yesterday", "by": "system"}], "assigned_to": "", "created_at": "Yesterday"},
                {"id": "FM-10246", "tenant_id": "tenant_fresh", "customer": "Kavya Nair", "phone": "+91 99820 11245", "items": [{"name": "Alphonso Mangoes", "qty": "2 kg", "price": 760}], "subtotal": 760, "discount": 0, "tax": 0, "delivery_charge": 0, "total": 760, "fulfilment": "HOME_DELIVERY", "payment": "PAID", "status": "PACKING", "address": "88 Besant Nagar, Chennai 600090", "pickup_code": "", "notes": "Deliver after 6 PM", "timeline": [{"status": "NEW", "at": "Today, 11:02 AM", "by": "system"}, {"status": "PACKING", "at": "Today, 11:14 AM", "by": "Divya"}], "assigned_to": "Divya", "created_at": "Today, 11:02 AM"},
            ])

        if await db.customers.count_documents({}) == 0:
            await db.customers.insert_many([
                {"id": "cust_1", "tenant_id": "tenant_fresh", "name": "Rahul Mehta", "phone": "+91 98765 43210", "orders_count": 12, "total_spent": 3450, "last_order_at": "Today, 10:42 AM", "tags": ["regular", "pickup"]},
                {"id": "cust_2", "tenant_id": "tenant_fresh", "name": "Priya Shah", "phone": "+91 98420 11032", "orders_count": 8, "total_spent": 1980, "last_order_at": "Today, 10:15 AM", "tags": ["regular", "delivery"]},
                {"id": "cust_3", "tenant_id": "tenant_fresh", "name": "Arjun Rao", "phone": "+91 99001 32211", "orders_count": 1, "total_spent": 125, "last_order_at": "Today, 09:58 AM", "tags": ["new"]},
                {"id": "cust_4", "tenant_id": "tenant_fresh", "name": "Neha Iyer", "phone": "+91 98880 44022", "orders_count": 5, "total_spent": 720, "last_order_at": "Yesterday", "tags": ["regular"]},
                {"id": "cust_5", "tenant_id": "tenant_fresh", "name": "Kavya Nair", "phone": "+91 99820 11245", "orders_count": 3, "total_spent": 1520, "last_order_at": "Today, 11:02 AM", "tags": ["vip"]},
                {"id": "cust_6", "tenant_id": "tenant_glow", "name": "Ananya Kapoor", "phone": "+91 98999 22001", "orders_count": 4, "total_spent": 4500, "last_order_at": "Yesterday", "tags": ["vip"]},
            ])

        if await db.conversations.count_documents({}) == 0:
            await db.conversations.insert_many([
                {"id": "conv_1", "tenant_id": "tenant_fresh", "customer": "Rahul Mehta", "phone": "+91 98765 43210", "linked_order_id": "FM-10245", "status": "active", "last_at": "Today, 10:42 AM", "messages": [
                    {"from": "customer", "body": "Hi, I want 2kg tomatoes, 1kg onions, 2kg potatoes", "at": "Today, 10:38 AM"},
                    {"from": "bot", "body": "🎉 Added to cart. Total ₹190. Home delivery or pickup?", "at": "Today, 10:39 AM"},
                    {"from": "customer", "body": "I'll collect from the store", "at": "Today, 10:40 AM"},
                    {"from": "bot", "body": "✅ Order FM-10245 confirmed for pickup at Fresh Mart T. Nagar.", "at": "Today, 10:42 AM"},
                ]},
                {"id": "conv_2", "tenant_id": "tenant_fresh", "customer": "Priya Shah", "phone": "+91 98420 11032", "linked_order_id": "FM-10244", "status": "active", "last_at": "Today, 10:15 AM", "messages": [
                    {"from": "customer", "body": "2 A2 milk please, deliver home", "at": "Today, 10:12 AM"},
                    {"from": "bot", "body": "🛵 Confirmed. Order FM-10244 out for delivery.", "at": "Today, 10:15 AM"},
                ]},
            ])

        # Demo tenant owner logins (password Owner123!) — only created alongside the demo tenants above.
        owners = [
            ("owner_fresh", "owner@freshmart.com", "Meera Krishnan", "tenant_fresh"),
            ("owner_glow", "owner@glowcosmetics.com", "Aditi Sharma", "tenant_glow"),
            ("owner_abc", "owner@abcpharmacy.com", "Sanjay Patel", "tenant_abc"),
        ]
        for uid, email, name, tid in owners:
            if not await db.users.find_one({"email": email}):
                await db.users.insert_one({"id": uid, "email": email, "name": name, "role": "TENANT_OWNER", "tenant_id": tid, "password_hash": hash_password("Owner123!")})

    # Real Master Admin login — always created regardless of SEED_DEMO_DATA.
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    if not await db.users.find_one({"email": admin_email}):
        await db.users.insert_one({"id": "user_master_admin", "email": admin_email, "name": "Arjun Shah", "role": "MASTER_ADMIN", "password_hash": hash_password(admin_password)})


@app.on_event("startup")
async def startup():
    await ensure_seed()


# ---------- Auth ----------
@api.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    user = await db.users.find_one({"email": payload.email.lower()})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect")
    access = create_token(user["id"], "access", 60 * 8)
    refresh = create_token(user["id"], "refresh", 60 * 24 * 7)
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=8 * 3600, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=7 * 24 * 3600, path="/")
    return {k: v for k, v in user.items() if k not in ["_id", "password_hash"]}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return user


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


# ---------- Master Admin ----------
def _clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc.pop("_id", None)
    return doc


def _tenant_summary(t: Dict[str, Any]) -> Dict[str, Any]:
    onb = t.get("onboarding", {})
    completed = sum(1 for v in onb.values() if v)
    total = max(len(onb), 1)
    return {
        "id": t["id"], "name": t["name"], "category": t["category"], "status": t.get("status"),
        "orders": t.get("orders", 0), "revenue": t.get("revenue", 0), "health": t.get("health", 0),
        "onboarding_progress": round(completed / total * 100),
        "whatsapp_connected": t.get("integrations", {}).get("whatsapp", {}).get("connected", False),
        "catalog_connected": t.get("integrations", {}).get("catalog", {}).get("connected", False),
    }


@api.get("/admin/overview")
async def admin_overview(user=Depends(master_user)):
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(500)
    summaries = [_tenant_summary(t) for t in tenants]
    total_tpl = await db.templates.count_documents({})
    total_users = await db.users.count_documents({"role": "TENANT_OWNER"})
    return {
        "tenants": summaries,
        "metrics": {
            "total_tenants": len(tenants),
            "active_tenants": sum(t.get("status") == "Active" for t in tenants),
            "onboarding_tenants": sum(t.get("status") == "Onboarding" for t in tenants),
            "platform_revenue": sum(t.get("revenue", 0) for t in tenants),
            "integration_health": 92,
            "automation_runs": 1842,
            "template_library": total_tpl,
            "owner_logins": total_users,
        },
    }


@api.get("/admin/tenants")
async def list_tenants(user=Depends(master_user)):
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(500)
    return [_tenant_summary(t) for t in tenants]


@api.get("/admin/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, user=Depends(master_user)):
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    owner = await db.users.find_one({"tenant_id": tenant_id, "role": "TENANT_OWNER"}, {"_id": 0, "password_hash": 0})
    tenant["owner"] = owner
    return tenant


@api.post("/admin/tenants", status_code=201)
async def create_tenant(payload: ClientCreateIn, user=Depends(master_user)):
    exists = await db.users.find_one({"email": payload.owner_email.lower()})
    if exists:
        raise HTTPException(400, "Owner email already registered")
    tid = new_id("tenant")
    cfg = default_tenant_config()
    cfg["business"].update({
        "description": payload.description, "phone": payload.phone, "email": payload.email,
        "city": payload.city, "state": payload.state, "pincode": payload.pincode,
        "currency": payload.currency, "timezone": payload.timezone,
    })
    await db.tenants.insert_one({
        "id": tid, "name": payload.business_name, "category": payload.category,
        "status": "Onboarding", "orders": 0, "revenue": 0, "health": 25, **cfg,
    })
    uid = new_id("owner")
    await db.users.insert_one({
        "id": uid, "email": payload.owner_email.lower(), "name": payload.owner_name,
        "role": "TENANT_OWNER", "tenant_id": tid, "password_hash": hash_password(payload.owner_password),
    })
    await audit(tid, user, "tenant.created", tid, {"business_name": payload.business_name})
    return {"tenant_id": tid, "owner_id": uid, "owner_email": payload.owner_email.lower()}


@api.patch("/admin/tenants/{tenant_id}")
async def patch_tenant(tenant_id: str, payload: TenantPatchIn, user=Depends(master_user)):
    updates: Dict[str, Any] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.category is not None:
        updates["category"] = payload.category
    for k in ["description", "phone", "email", "city", "state", "pincode"]:
        v = getattr(payload, k)
        if v is not None:
            updates[f"business.{k}"] = v
    if updates:
        await db.tenants.update_one({"id": tenant_id}, {"$set": updates})
        await audit(tenant_id, user, "tenant.updated", tenant_id, updates)
    return await db.tenants.find_one({"id": tenant_id}, {"_id": 0})


async def _mark_onboarding(tenant_id: str, key: str, value: bool = True):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {f"onboarding.{key}": value}})
    tenant = await db.tenants.find_one({"id": tenant_id})
    if tenant:
        onb = tenant.get("onboarding", {})
        completed = sum(1 for v in onb.values() if v)
        total = max(len(onb), 1)
        await db.tenants.update_one({"id": tenant_id}, {"$set": {"health": round(completed / total * 100)}})


@api.post("/admin/tenants/{tenant_id}/whatsapp")
async def configure_whatsapp(tenant_id: str, payload: WhatsAppConfigIn, user=Depends(master_user)):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {
        "integrations.whatsapp": {"connected": True, "phone_number": payload.phone_number, "business_account_id": payload.business_account_id, "provider": payload.provider, "status": "Connected"}
    }})
    await _mark_onboarding(tenant_id, "whatsapp_connected", True)
    await audit(tenant_id, user, "whatsapp.configured", tenant_id, payload.model_dump())
    return {"ok": True}


@api.post("/admin/tenants/{tenant_id}/catalog")
async def configure_catalog(tenant_id: str, payload: CatalogConfigIn, user=Depends(master_user)):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {
        "integrations.catalog": {"connected": True, "source": payload.source, "external_id": payload.external_id, "last_synced": now_iso()}
    }})
    await _mark_onboarding(tenant_id, "catalog_connected", True)
    await audit(tenant_id, user, "catalog.configured", tenant_id, payload.model_dump())
    return {"ok": True}


@api.post("/admin/tenants/{tenant_id}/payment")
async def configure_payment(tenant_id: str, payload: PaymentConfigIn, user=Depends(master_user)):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {
        "integrations.payment": {"provider": payload.provider, "mode": "test", "cod_enabled": payload.cod_enabled, "upi_enabled": payload.upi_enabled, "online_enabled": payload.online_enabled, "configured": True}
    }})
    await _mark_onboarding(tenant_id, "payment_configured", True)
    await audit(tenant_id, user, "payment.configured", tenant_id, payload.model_dump())
    return {"ok": True}


@api.post("/admin/tenants/{tenant_id}/fulfilment")
async def configure_fulfilment(tenant_id: str, payload: FulfilmentConfigIn, user=Depends(master_user)):
    locations = payload.pickup_locations
    if not locations:
        locations = [{"id": "loc_main", "name": payload.pickup_location_name, "address": payload.pickup_address, "hours": payload.pickup_hours}]
    else:
        # ensure every location has an id
        locations = [{**l, "id": l.get("id") or new_id("loc")} for l in locations]
    await db.tenants.update_one({"id": tenant_id}, {"$set": {
        "fulfilment": {
            "home_delivery": {"enabled": payload.delivery_enabled, "base_charge": payload.delivery_charge, "free_above": payload.delivery_free_above, "min_order": payload.min_order, "zones": payload.delivery_zones},
            "store_pickup": {"enabled": payload.pickup_enabled, "location": locations[0], "locations": locations, "preparation_minutes": payload.preparation_minutes},
        }
    }})
    await _mark_onboarding(tenant_id, "fulfilment_configured", True)
    await audit(tenant_id, user, "fulfilment.configured", tenant_id, payload.model_dump())
    return {"ok": True}


@api.post("/admin/tenants/{tenant_id}/templates/apply")
async def apply_templates(tenant_id: str, user=Depends(master_user)):
    ids = [t["id"] for t in await db.templates.find({}, {"id": 1, "_id": 0}).to_list(500)]
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"templates": ids}})
    await _mark_onboarding(tenant_id, "templates_configured", True)
    await audit(tenant_id, user, "templates.applied", tenant_id, {"count": len(ids)})
    return {"ok": True, "applied": len(ids)}


@api.post("/admin/tenants/{tenant_id}/automations/apply")
async def apply_automations(tenant_id: str, user=Depends(master_user)):
    automations = [{"id": new_id("aut"), **a, "enabled": True} for a in DEFAULT_AUTOMATIONS]
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"automations": automations}})
    await _mark_onboarding(tenant_id, "automations_configured", True)
    await audit(tenant_id, user, "automations.applied", tenant_id, {"count": len(automations)})
    return {"ok": True, "applied": len(automations)}


@api.post("/admin/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, user=Depends(master_user)):
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    onb = tenant.get("onboarding", {})
    required = ["whatsapp_connected", "catalog_connected", "templates_configured", "payment_configured", "fulfilment_configured"]
    missing = [k for k in required if not onb.get(k)]
    if missing:
        raise HTTPException(400, f"Missing setup: {', '.join(missing)}")
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"status": "Active", "onboarding.ready_to_go_live": True, "health": 100}})
    await audit(tenant_id, user, "tenant.activated", tenant_id, {})
    return {"ok": True}


@api.post("/admin/tenants/{tenant_id}/deactivate")
async def deactivate_tenant(tenant_id: str, user=Depends(master_user)):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"status": "Suspended"}})
    await audit(tenant_id, user, "tenant.deactivated", tenant_id, {})
    return {"ok": True}


@api.get("/admin/templates")
async def list_templates(user=Depends(master_user)):
    return await db.templates.find({}, {"_id": 0}).to_list(500)


@api.post("/admin/templates", status_code=201)
async def create_template(payload: TemplateIn, user=Depends(master_user)):
    doc = {"id": new_id("tpl"), **payload.model_dump()}
    await db.templates.insert_one(doc)
    await audit(None, user, "template.created", doc["id"], {"name": payload.name})
    return _clean(dict(doc))


@api.get("/admin/integrations")
async def integrations_health(user=Depends(master_user)):
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(500)
    whatsapp = sum(1 for t in tenants if t.get("integrations", {}).get("whatsapp", {}).get("connected"))
    catalog = sum(1 for t in tenants if t.get("integrations", {}).get("catalog", {}).get("connected"))
    payment = sum(1 for t in tenants if t.get("integrations", {}).get("payment", {}).get("configured"))
    return {
        "whatsapp": {"connected": whatsapp, "total": len(tenants), "provider": "Meta Cloud API"},
        "catalog": {"connected": catalog, "total": len(tenants), "provider": "Internal"},
        "payment": {"connected": payment, "total": len(tenants), "provider": "Razorpay test"},
    }


@api.get("/admin/analytics")
async def platform_analytics(user=Depends(master_user)):
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(500)
    return {
        "by_tenant": [{"name": t["name"], "orders": t.get("orders", 0), "revenue": t.get("revenue", 0)} for t in tenants],
        "totals": {"tenants": len(tenants), "orders": sum(t.get("orders", 0) for t in tenants), "revenue": sum(t.get("revenue", 0) for t in tenants)},
        "growth": {"tenants_this_month": 2, "revenue_growth": 18},
    }


@api.get("/admin/audit")
async def audit_feed(user=Depends(master_user)):
    return await db.audit_logs.find({}, {"_id": 0}).sort("at", -1).to_list(100)


# ---------- Client Workspace ----------
@api.get("/workspace/overview")
async def workspace_overview(user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    tenant = await db.tenants.find_one({"id": tid}, {"_id": 0})
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    orders = await db.orders.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    products = await db.products.find({"tenant_id": tid}, {"_id": 0}).to_list(500)
    customers_count = await db.customers.count_documents({"tenant_id": tid})
    return {
        "tenant": {k: v for k, v in tenant.items() if k not in ["templates", "automations"]},
        "orders": orders[:8],
        "products": products,
        "metrics": {
            "today_orders": len(orders),
            "revenue": sum(o.get("total", 0) for o in orders),
            "ready_pickup": sum(o.get("status") == "READY_FOR_PICKUP" for o in orders),
            "out_delivery": sum(o.get("status") == "OUT_FOR_DELIVERY" for o in orders),
            "new_orders": sum(o.get("status") == "NEW" for o in orders),
            "low_stock": sum(0 < p.get("stock", 0) < 20 for p in products),
            "out_stock": sum(p.get("stock", 0) == 0 for p in products),
            "customers": customers_count,
        },
    }


@api.get("/workspace/products")
async def workspace_products(user=Depends(tenant_owner)):
    return await db.products.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).to_list(500)


@api.post("/workspace/products", status_code=201)
async def create_product(product: ProductIn, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    doc = product.model_dump()
    doc.update({"id": new_id("prod"), "tenant_id": tid})
    doc["status"] = "Out of stock" if doc["stock"] == 0 else ("Low stock" if doc["stock"] < 20 else "Available")
    await db.products.insert_one(doc)
    await audit(tid, user, "product.created", doc["id"], {"name": doc["name"]})
    return _clean(doc)


@api.patch("/workspace/products/{product_id}")
async def patch_product(product_id: str, payload: ProductPatch, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "stock" in updates:
        stock = updates["stock"]
        updates["status"] = "Out of stock" if stock == 0 else ("Low stock" if stock < 20 else "Available")
    if not updates:
        raise HTTPException(400, "Nothing to update")
    result = await db.products.find_one_and_update(
        {"id": product_id, "tenant_id": tid}, {"$set": updates},
        return_document=ReturnDocument.AFTER, projection={"_id": 0},
    )
    if not result:
        raise HTTPException(404, "Product not found")
    await audit(tid, user, "product.updated", product_id, updates)
    return result


@api.delete("/workspace/products/{product_id}")
async def delete_product(product_id: str, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    res = await db.products.delete_one({"id": product_id, "tenant_id": tid})
    if not res.deleted_count:
        raise HTTPException(404, "Product not found")
    await audit(tid, user, "product.deleted", product_id, {})
    return {"ok": True}


@api.get("/workspace/orders")
async def workspace_orders(user=Depends(tenant_owner), status: Optional[str] = None, fulfilment: Optional[str] = None):
    tid = user["tenant_id"]
    q: Dict[str, Any] = {"tenant_id": tid}
    if status:
        q["status"] = status
    if fulfilment:
        q["fulfilment"] = fulfilment
    return await db.orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.get("/workspace/orders/{order_id}")
async def workspace_order(order_id: str, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    order = await db.orders.find_one({"id": order_id, "tenant_id": tid}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    return order


VALID_TRANSITIONS = {
    "NEW": ["PICKING", "CANCELLED"],
    "PICKING": ["PACKING", "CANCELLED"],
    "PACKING": ["READY_FOR_PICKUP", "READY_FOR_DISPATCH", "OUT_FOR_DELIVERY", "CANCELLED"],
    "READY_FOR_PICKUP": ["COLLECTED", "COMPLETED", "CANCELLED"],
    "READY_FOR_DISPATCH": ["OUT_FOR_DELIVERY", "CANCELLED"],
    "OUT_FOR_DELIVERY": ["DELIVERED", "COMPLETED"],
    "DELIVERED": ["COMPLETED"],
    "COLLECTED": ["COMPLETED"],
    "COMPLETED": [],
    "CANCELLED": [],
}


@api.patch("/workspace/orders/{order_id}/status")
async def update_order_status(order_id: str, payload: OrderStatusIn, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    order = await db.orders.find_one({"id": order_id, "tenant_id": tid})
    if not order:
        raise HTTPException(404, "Order not found")
    current = order.get("status", "NEW")
    allowed = VALID_TRANSITIONS.get(current, [])
    if payload.status not in allowed and payload.status != current:
        raise HTTPException(400, f"Cannot move from {current} to {payload.status}")
    entry = {"status": payload.status, "at": datetime.now(timezone.utc).strftime("Today, %I:%M %p"), "by": user["name"], "note": payload.note or ""}
    result = await db.orders.find_one_and_update(
        {"id": order_id, "tenant_id": tid},
        {"$set": {"status": payload.status}, "$push": {"timeline": entry}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0},
    )
    # Release reserved stock back to inventory on cancellation — checkout
    # decremented `stock` directly, so cancelling must add it back or every
    # cancelled order permanently shrinks the count.
    if payload.status == "CANCELLED" and current != "CANCELLED":
        for item in order.get("items", []):
            sku = item.get("sku")
            qty = item.get("qty", 0)
            if sku and qty:
                await db.products.update_one({"tenant_id": tid, "sku": sku}, {"$inc": {"stock": qty}})
    await audit(tid, user, "order.status_changed", order_id, {"from": current, "to": payload.status})
    # Fire WhatsApp status notification (invoice PDF auto-generated on DELIVERED/COLLECTED).
    from commerce_ops import notify_status_change
    try:
        notify = await notify_status_change(db, tid, order_id, payload.status, actor_name=user["name"])
        if notify.get("invoice_url"):
            result["invoice_url"] = notify["invoice_url"]
    except Exception as e:
        import logging
        logging.exception("notify_status_change failed for %s: %s", order_id, e)
    return result


@api.post("/workspace/orders/{order_id}/notes")
async def add_note(order_id: str, payload: OrderNoteIn, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    key = "internal_notes" if payload.kind == "internal" else "customer_notes"
    entry = {"note": payload.note, "at": now_iso(), "by": user["name"]}
    result = await db.orders.find_one_and_update(
        {"id": order_id, "tenant_id": tid}, {"$push": {key: entry}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0},
    )
    if not result:
        raise HTTPException(404, "Order not found")
    return result


@api.post("/workspace/orders/{order_id}/assign")
async def assign_order(order_id: str, payload: OrderAssignIn, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    result = await db.orders.find_one_and_update(
        {"id": order_id, "tenant_id": tid}, {"$set": {"assigned_to": payload.staff_name}},
        return_document=ReturnDocument.AFTER, projection={"_id": 0},
    )
    if not result:
        raise HTTPException(404, "Order not found")
    await audit(tid, user, "order.assigned", order_id, {"staff": payload.staff_name})
    return result


@api.post("/workspace/orders", status_code=201)
async def create_manual_order(payload: ManualOrderIn, user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    subtotal = sum(i.get("price", 0) for i in payload.items)
    tenant = await db.tenants.find_one({"id": tid})
    delivery_charge = 0
    if payload.fulfilment == "HOME_DELIVERY":
        d = tenant.get("fulfilment", {}).get("home_delivery", {})
        delivery_charge = 0 if subtotal >= d.get("free_above", 0) else d.get("base_charge", 0)
    seq = await db.orders.count_documents({"tenant_id": tid}) + 1
    order_id = f"{tenant['name'][:2].upper()}-{10000 + seq}"
    doc = {
        "id": order_id, "tenant_id": tid, "customer": payload.customer, "phone": payload.phone,
        "items": payload.items, "subtotal": subtotal, "discount": 0, "tax": 0,
        "delivery_charge": delivery_charge, "total": subtotal + delivery_charge,
        "fulfilment": payload.fulfilment, "payment": payload.payment, "status": "NEW",
        "address": payload.address, "pickup_code": f"PC{uuid.uuid4().hex[:4].upper()}" if payload.fulfilment == "STORE_PICKUP" else "",
        "notes": "", "assigned_to": "",
        "timeline": [{"status": "NEW", "at": datetime.now(timezone.utc).strftime("Today, %I:%M %p"), "by": user["name"]}],
        "created_at": datetime.now(timezone.utc).strftime("Today, %I:%M %p"),
    }
    await db.orders.insert_one(doc)
    await audit(tid, user, "order.created", order_id, {"customer": payload.customer})
    return _clean(dict(doc))


@api.get("/workspace/customers")
async def workspace_customers(user=Depends(tenant_owner)):
    return await db.customers.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("last_order_at", -1).to_list(500)


@api.get("/workspace/conversations")
async def workspace_conversations(user=Depends(tenant_owner)):
    return await db.conversations.find({"tenant_id": user["tenant_id"]}, {"_id": 0}).sort("last_at", -1).to_list(200)


@api.get("/workspace/settings")
async def workspace_settings(user=Depends(tenant_owner)):
    tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return {
        "business": tenant.get("business", {}),
        "fulfilment": tenant.get("fulfilment", {}),
        "integrations": tenant.get("integrations", {}),
        "templates_count": len(tenant.get("templates", [])),
        "automations": tenant.get("automations", []),
    }


@api.get("/workspace/fulfilment/queues")
async def fulfilment_queues(user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    orders = await db.orders.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    def bucket(statuses):
        return [o for o in orders if o.get("status") in statuses]
    return {
        "NEW": bucket(["NEW"]),
        "PICKING": bucket(["PICKING"]),
        "PACKING": bucket(["PACKING"]),
        "READY_FOR_PICKUP": bucket(["READY_FOR_PICKUP"]),
        "READY_FOR_DISPATCH": bucket(["READY_FOR_DISPATCH"]),
        "OUT_FOR_DELIVERY": bucket(["OUT_FOR_DELIVERY"]),
        "COMPLETED": bucket(["COMPLETED", "DELIVERED", "COLLECTED"]),
    }


@api.get("/workspace/analytics")
async def workspace_analytics(user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    orders = await db.orders.find({"tenant_id": tid}, {"_id": 0}).to_list(500)
    products = await db.products.find({"tenant_id": tid}, {"_id": 0}).to_list(500)
    revenue = sum(o.get("total", 0) for o in orders)
    pickup = [o for o in orders if o.get("fulfilment") == "STORE_PICKUP"]
    delivery = [o for o in orders if o.get("fulfilment") == "HOME_DELIVERY"]
    return {
        "totals": {
            "orders": len(orders), "revenue": revenue,
            "avg_order": round(revenue / max(len(orders), 1)),
            "pickup_orders": len(pickup), "delivery_orders": len(delivery),
            "delivery_revenue": sum(o.get("delivery_charge", 0) for o in delivery),
        },
        "top_products": sorted(products, key=lambda p: -p.get("stock", 0))[:5],
        "recent_orders": orders[:6],
    }


# Delivery route board: geocode by hashing address into a bounding box around tenant's city.
_CITY_CENTERS = {
    "Chennai": (13.0827, 80.2707), "Mumbai": (19.076, 72.8777), "Bengaluru": (12.9716, 77.5946),
    "Delhi": (28.6139, 77.209), "Hyderabad": (17.385, 78.4867), "Pune": (18.5204, 73.8567),
}


def _fake_geocode(address: str, city: str) -> Dict[str, float]:
    import hashlib as _h
    lat0, lng0 = _CITY_CENTERS.get(city, (13.0827, 80.2707))
    h = _h.sha256((address or "").encode()).digest()
    lat = lat0 + ((h[0] - 128) / 128.0) * 0.08
    lng = lng0 + ((h[1] - 128) / 128.0) * 0.08
    return {"lat": round(lat, 5), "lng": round(lng, 5)}


@api.get("/workspace/delivery-route")
async def delivery_route(user=Depends(tenant_owner)):
    tid = user["tenant_id"]
    tenant = await db.tenants.find_one({"id": tid}, {"_id": 0})
    city = (tenant or {}).get("business", {}).get("city", "Chennai")
    center = _CITY_CENTERS.get(city, (13.0827, 80.2707))
    orders = await db.orders.find({"tenant_id": tid, "fulfilment": "HOME_DELIVERY", "status": {"$in": ["READY_FOR_DISPATCH", "OUT_FOR_DELIVERY", "PACKING"]}}, {"_id": 0}).to_list(200)
    for o in orders:
        o.update(_fake_geocode(o.get("address", ""), city))
    # Sort by lat then lng (naive greedy sequencing)
    orders.sort(key=lambda o: (o["lat"], o["lng"]))
    return {"center": {"lat": center[0], "lng": center[1]}, "orders": orders, "city": city}


@api.get("/workspace/offers")
async def workspace_offers(user=Depends(tenant_owner)):
    return await db.products.find({"tenant_id": user["tenant_id"], "is_offer": True}, {"_id": 0}).to_list(200)


app.include_router(api)

# Extended commerce services: cart engine, WhatsApp webhook + simulator,
# payments (Razorpay + COD), industry template packs.
from commerce_ext import build_router as _build_ext
_ext_router = _build_ext(db, master_user, tenant_owner, audit)
app.include_router(_ext_router, prefix="/api")

# Invoicing, status notifications, abandoned-cart engine.
from commerce_ops import build_router as _build_ops, periodic_scan_task as _scan_task
_ops_router, _scan_fn = _build_ops(db, master_user, tenant_owner, audit)
app.include_router(_ops_router, prefix="/api")


@app.on_event("startup")
async def _start_scan_task():
    import asyncio
    app.state.abandoned_task = asyncio.create_task(_scan_task(_scan_fn))


@app.on_event("shutdown")
async def _stop_scan_task():
    task = getattr(app.state, "abandoned_task", None)
    if task:
        task.cancel()


app.add_middleware(
    CORSMiddleware, allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown():
    client.close()
