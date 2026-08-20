"""Invoice PDF generator, status notifications, abandoned cart engine.
All three services attach to the same tenant + WhatsApp + template pipeline that
commerce_ext.py already established."""
import asyncio
import hashlib
import hmac
import io
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Relative to this file, not hardcoded to Emergent's /app/backend container path —
# on Render (or anywhere else) the app root differs, and os.makedirs() on an
# absolute path outside the writable tree crashes at import time.
INVOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invoices")
os.makedirs(INVOICES_DIR, exist_ok=True)

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist_display() -> str:
    return datetime.now(IST).strftime("Today, %I:%M %p")



# --------- Invoice signing (public download link) ---------
def _sign(order_id: str) -> str:
    secret = os.environ.get("INVOICE_SIGNING_SECRET", "changeme").encode()
    return hmac.new(secret, order_id.encode(), hashlib.sha256).hexdigest()[:24]


def invoice_download_url(order_id: str) -> str:
    base = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
    return f"{base}/api/public/invoice/{order_id}/{_sign(order_id)}"


# --------- PDF renderer ---------
def render_invoice_pdf(tenant: Dict[str, Any], order: Dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#475569"))
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#94a3b8"), spaceAfter=2)
    heading = ParagraphStyle("heading", parent=styles["Heading1"], fontSize=22, textColor=colors.HexColor("#0f172a"), leading=26, spaceAfter=2)
    business = tenant.get("business", {})

    story = []
    # Header row
    header = Table([[
        Paragraph(f"<b>{tenant['name']}</b><br/><font size=8 color='#64748b'>{business.get('description','')}<br/>{business.get('city','')}, {business.get('state','')} · {business.get('pincode','')}<br/>{business.get('phone','')} · {business.get('email','')}</font>", styles["Normal"]),
        Paragraph(f"<para align='right'><b>INVOICE</b><br/><font size=8 color='#64748b'>{order['id']}<br/>{order.get('created_at','')}</font></para>", styles["Normal"]),
    ]], colWidths=[110 * mm, 62 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 8 * mm))

    # Customer + fulfilment strip
    fulfilment = order.get("fulfilment", "").replace("_", " ").title()
    payment_status = order.get("payment", "PENDING")
    address = order.get("address") or "-"
    if order.get("fulfilment") == "STORE_PICKUP":
        loc = tenant.get("fulfilment", {}).get("store_pickup", {}).get("location", {})
        address = f"{loc.get('name','Store')} · {loc.get('address','')}"
    meta = Table([
        [Paragraph("BILLED TO", label), Paragraph("FULFILMENT", label), Paragraph("PAYMENT", label)],
        [Paragraph(f"<b>{order['customer']}</b><br/>{order['phone']}<br/><font size=8>{address}</font>", small),
         Paragraph(f"<b>{fulfilment}</b><br/><font size=8>{'Pickup code ' + order.get('pickup_code','') if order.get('pickup_code') else 'Delivery'}</font>", small),
         Paragraph(f"<b>{payment_status}</b><br/><font size=8>Order status: {order.get('status','').replace('_',' ')}</font>", small)],
    ], colWidths=[70 * mm, 55 * mm, 47 * mm])
    meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta)
    story.append(Spacer(1, 8 * mm))

    # Items table
    items_data = [["ITEM", "QTY", "AMOUNT"]]
    for it in order.get("items", []):
        items_data.append([it["name"], it.get("qty", ""), f"₹{it.get('price', 0):,.2f}"])
    items = Table(items_data, colWidths=[110 * mm, 30 * mm, 32 * mm])
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]))
    story.append(items)
    story.append(Spacer(1, 6 * mm))

    # Totals
    subtotal = order.get("subtotal", 0)
    delivery = order.get("delivery_charge", 0)
    total = order.get("total", subtotal + delivery)
    totals_rows = [
        ["Subtotal", f"₹{subtotal:,.2f}"],
        ["Delivery", f"₹{delivery:,.2f}"] if delivery else None,
        ["Total", f"₹{total:,.2f}"],
    ]
    totals_rows = [r for r in totals_rows if r]
    totals = Table(totals_rows, colWidths=[110 * mm, 62 * mm])
    totals.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#0f172a")),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#0f172a")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(totals)
    story.append(Spacer(1, 12 * mm))

    story.append(Paragraph(
        f"<font color='#64748b' size=8>Thank you for shopping with <b>{tenant['name']}</b>. Powered by Commerce OS.</font>",
        small))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


async def build_and_save_invoice(db, tenant_id: str, order_id: str) -> Dict[str, Any]:
    tenant = await db.tenants.find_one({"id": tenant_id})
    order = await db.orders.find_one({"id": order_id, "tenant_id": tenant_id})
    if not tenant or not order:
        raise HTTPException(404, "Order or tenant not found")
    pdf = render_invoice_pdf(tenant, order)
    path = os.path.join(INVOICES_DIR, f"{order_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf)
    url = invoice_download_url(order_id)
    await db.orders.update_one({"id": order_id, "tenant_id": tenant_id}, {"$set": {
        "invoice_url": url, "invoice_generated_at": datetime.now(timezone.utc).isoformat()
    }})
    return {"url": url, "path": path}


# --------- WhatsApp sender + status notifications ---------
async def _send_whatsapp(tenant: Dict[str, Any], to: str, body: str) -> Dict[str, Any]:
    from commerce_ext import decrypt as _decrypt
    wa = tenant.get("integrations", {}).get("whatsapp", {})
    if not wa.get("access_token_enc") or not wa.get("phone_number_id"):
        return {"ok": False, "reason": "not_configured"}
    try:
        token = _decrypt(wa["access_token_enc"])
    except Exception:
        return {"ok": False, "reason": "invalid_creds"}
    url = f"https://graph.facebook.com/v23.0/{wa['phone_number_id']}/messages"
    async with httpx.AsyncClient(timeout=8.0) as http:
        r = await http.post(url, headers={"Authorization": f"Bearer {token}"},
                            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}})
    if r.status_code >= 400:
        return {"ok": False, "reason": r.text[:200]}
    return {"ok": True}


STATUS_TEMPLATES = {
    "PICKING": "🛒 Your order {order_id} is being picked from the shelves.",
    "PACKING": "📦 Your order {order_id} is being packed with care.",
    "READY_FOR_PICKUP": "✅ Your order {order_id} is ready for pickup at {store}. Show pickup code *{pickup_code}* on arrival.",
    "READY_FOR_DISPATCH": "🛵 Your order {order_id} is packed and ready to dispatch.",
    "OUT_FOR_DELIVERY": "🚚 Your order {order_id} is on the way!",
    "DELIVERED": "✅ Your order {order_id} has been delivered. Invoice: {invoice_url}",
    "COLLECTED": "✅ Order {order_id} collected. Thank you! Invoice: {invoice_url}",
    "COMPLETED": "🎉 Order {order_id} is complete. Thank you for shopping with {business}!",
    "CANCELLED": "❌ Your order {order_id} has been cancelled. Please contact us if this is unexpected.",
}


async def _log_bot_message(db, tenant_id: str, phone: str, customer: str, body: str, order_id: str = ""):
    ts = now_ist_display()
    message = {"from": "bot", "body": body, "at": ts}
    existing = await db.conversations.find_one({"tenant_id": tenant_id, "phone": phone}, {"_id": 0})
    if existing:
        upd: Dict[str, Any] = {"$push": {"messages": message}, "$set": {"last_at": ts}}
        if order_id:
            upd["$set"]["linked_order_id"] = order_id
        await db.conversations.update_one({"id": existing["id"]}, upd)
    else:
        await db.conversations.insert_one({
            "id": f"conv_{order_id or phone[-6:]}", "tenant_id": tenant_id, "customer": customer, "phone": phone,
            "linked_order_id": order_id, "status": "active", "last_at": ts, "messages": [message],
        })


async def notify_status_change(db, tenant_id: str, order_id: str, new_status: str, actor_name: str = "system") -> Dict[str, Any]:
    """Send a WhatsApp status update to the customer. Auto-generates an invoice
    when status is DELIVERED or COLLECTED."""
    order = await db.orders.find_one({"id": order_id, "tenant_id": tenant_id}, {"_id": 0})
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not order or not tenant:
        return {"sent": False, "reason": "not_found"}

    invoice_url = ""
    if new_status in ("DELIVERED", "COLLECTED"):
        info = await build_and_save_invoice(db, tenant_id, order_id)
        invoice_url = info["url"]

    tpl = STATUS_TEMPLATES.get(new_status)
    if not tpl:
        return {"sent": False, "reason": "no_template"}
    store_loc = tenant.get("fulfilment", {}).get("store_pickup", {}).get("location", {})
    body = tpl.format(
        order_id=order_id,
        store=store_loc.get("name", "the store"),
        pickup_code=order.get("pickup_code", ""),
        invoice_url=invoice_url or "(available shortly)",
        business=tenant["name"],
    )
    await _log_bot_message(db, tenant_id, order["phone"], order["customer"], body, order_id=order_id)
    result = await _send_whatsapp(tenant, order["phone"], body)
    return {"sent": result["ok"], "reason": result.get("reason", ""), "message": body, "invoice_url": invoice_url}


# --------- Router with public invoice + abandoned cart endpoints ---------
def build_router(db, master_user_dep, tenant_owner_dep, audit_fn):
    router = APIRouter()

    @router.get("/public/invoice/{order_id}/{signature}")
    async def public_invoice(order_id: str, signature: str):
        if not hmac.compare_digest(signature, _sign(order_id)):
            raise HTTPException(403, "invalid signature")
        path = os.path.join(INVOICES_DIR, f"{order_id}.pdf")
        if not os.path.exists(path):
            # Regenerate on demand (in case of storage loss).
            order = await db.orders.find_one({"id": order_id})
            if not order:
                raise HTTPException(404, "invoice not available")
            await build_and_save_invoice(db, order["tenant_id"], order_id)
        with open(path, "rb") as fh:
            data = fh.read()
        return Response(content=data, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{order_id}.pdf"',
        })

    @router.post("/workspace/orders/{order_id}/invoice")
    async def regenerate_invoice(order_id: str, user=Depends(tenant_owner_dep)):
        info = await build_and_save_invoice(db, user["tenant_id"], order_id)
        return {"invoice_url": info["url"]}

    @router.get("/workspace/orders/{order_id}/invoice.pdf")
    async def download_invoice(order_id: str, user=Depends(tenant_owner_dep)):
        order = await db.orders.find_one({"id": order_id, "tenant_id": user["tenant_id"]})
        if not order:
            raise HTTPException(404, "Order not found")
        path = os.path.join(INVOICES_DIR, f"{order_id}.pdf")
        if not os.path.exists(path):
            await build_and_save_invoice(db, user["tenant_id"], order_id)
        with open(path, "rb") as fh:
            data = fh.read()
        return Response(content=data, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{order_id}.pdf"',
        })

    # -------- Abandoned cart --------
    async def _scan_abandoned_carts_once() -> Dict[str, Any]:
        hours = float(os.environ.get("ABANDONED_CART_HOURS", "2"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_iso = cutoff.isoformat()
        carts = await db.carts.find({
            "status": "active",
            "items": {"$ne": []},
            "$and": [
                {"$or": [{"nudged_at": {"$exists": False}}, {"nudged_at": None}]},
                {"updated_at": {"$lt": cutoff_iso}},
            ],
        }, {"_id": 0}).to_list(200)
        nudged = 0
        for cart in carts:
            tenant = await db.tenants.find_one({"id": cart["tenant_id"]}, {"_id": 0})
            if not tenant:
                continue
            body = f"👋 Hi {cart.get('customer','friend')}, you still have items in your {tenant['name']} cart. Reply *cart* to review or *confirm* to place the order."
            await _log_bot_message(db, cart["tenant_id"], cart["phone"], cart.get("customer", cart["phone"]), body)
            await _send_whatsapp(tenant, cart["phone"], body)
            await db.carts.update_one({"id": cart["id"]}, {"$set": {"nudged_at": datetime.now(timezone.utc).isoformat()}})
            nudged += 1
        return {"scanned": len(carts), "nudged": nudged}

    @router.post("/admin/carts/abandoned/scan")
    async def scan_abandoned(user=Depends(master_user_dep)):
        return await _scan_abandoned_carts_once()

    @router.get("/admin/carts/abandoned")
    async def list_abandoned(user=Depends(master_user_dep)):
        hours = float(os.environ.get("ABANDONED_CART_HOURS", "2"))
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        carts = await db.carts.find({"status": "active", "items": {"$ne": []}, "updated_at": {"$lt": cutoff}}, {"_id": 0}).sort("updated_at", -1).to_list(100)
        # Enrich with tenant name.
        tenants = {t["id"]: t["name"] for t in await db.tenants.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
        return [{"id": c["id"], "tenant": tenants.get(c["tenant_id"], "?"), "customer": c.get("customer"), "phone": c["phone"], "items": len(c.get("items", [])), "updated_at": c.get("updated_at"), "nudged_at": c.get("nudged_at")} for c in carts]

    return router, _scan_abandoned_carts_once


# --------- Background task: periodic abandoned-cart scan ---------
async def periodic_scan_task(scan_fn):
    while True:
        try:
            await asyncio.sleep(60 * 15)  # every 15 minutes
            await scan_fn()
        except asyncio.CancelledError:  # pragma: no cover
            break
        except Exception:  # noqa: BLE001
            # never crash the loop
            await asyncio.sleep(60)
