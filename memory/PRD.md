# Commerce OS — Multi-Tenant WhatsApp Commerce Operating System

## Original problem statement
Production-ready, industry-agnostic multi-tenant WhatsApp Commerce OS with:
- **Master Admin SaaS** (platform owner): onboarding, integrations, templates, automations, activation, platform analytics, audit. No client operational data.
- **Client Workspace SaaS** (tenant owner): products, inventory, orders, fulfilment (delivery + pickup), customers, WhatsApp conversations, analytics, settings.
- Backend-enforced tenant isolation, one owner login per client (MVP).

## Architecture
- **Backend**: FastAPI + MongoDB (Motor). Auth is cookie-based JWT (`access_token`/`refresh_token`, secure, samesite=none).
- **Frontend**: React 19 (CRA/CRACO), modular pages under `/pages/master` and `/pages/client`, shared components under `/components/shared`, thin `App.js` router.
- **Multi-tenancy**: Every tenant-scoped collection carries `tenant_id`; workspace endpoints derive tenant only from authenticated user (never from headers/frontend).
- **State machine**: Order status transitions enforced by `VALID_TRANSITIONS` map in `server.py`. Delivery and pickup follow different paths.

## User personas
- **Master Admin**: platform owner. Creates clients, connects integrations, applies templates & automations, activates workspaces.
- **Tenant Owner**: single owner login per client (MVP). Runs day-to-day commerce operations.
- Future: Packer, Delivery Staff, Pickup Staff, Order Manager, Customer Support.

## Core requirements (static)
- Two isolated SaaS experiences under one platform. No cross-tenant visibility.
- Central commerce engine that will power WhatsApp first, other channels later.
- Fulfilment supports home delivery **and** store pickup per tenant.
- Configurable delivery charges, free-above threshold, min order, delivery zones.
- Store pickup: location, hours, prep time, pickup code.
- Idempotent order creation, safe status transitions, audit log.
- Backend-enforced role and tenant boundaries.

## What has been implemented (2026-02-16, updated iteration_4)
### Backend
- **`server.py`**: Auth (cookie JWT), Master Admin CRUD + configuration, Client Workspace endpoints, audit log.
- **`commerce_ext.py`** (new): reusable extension router mounted at `/api`:
  - **Cart engine** (`/cart/*`): `session`, add/update/remove items, clear, `fulfilment` (HOME_DELIVERY|STORE_PICKUP), `checkout`. Live stock+price re-validation on every read. Tenant-configurable delivery charge (base + free-above threshold). Checkout reserves stock atomically per product, upserts customer, creates order + timeline, and lands it in the fulfilment queue. Cart-order link retained on the order + conversation.
  - **WhatsApp webhook scaffold** (`/webhooks/whatsapp`): Meta GET verify + POST signature verification (`X-Hub-Signature-256`, HMAC-SHA256 with `META_APP_SECRET`). Per-tenant credentials (`access_token` encrypted with Fernet) saved via `/admin/tenants/{id}/whatsapp-creds`. Tenant routing via `metadata.phone_number_id`.
  - **WhatsApp simulator** (`/admin/whatsapp/simulate`) — Master Admin only. Rule-based chatbot state machine: `hi/hello → welcome`, `shop → catalog`, `add <sku> [qty]`, `cart`, `delivery/pickup`, free-form address, `confirm → checkout → order`.
  - **Payments** (`/workspace/payments/intent` + `/workspace/payments/status/{id}` + `/webhooks/stripe` + `/webhooks/razorpay`): Stripe active via `emergentintegrations.payments.stripe.checkout`. Razorpay adapter fully wired (create order, verify webhook signature) — activates when `RAZORPAY_KEY_ID/SECRET` present. `cod` also supported.
  - **Industry template packs** (`/admin/template-packs`, `/admin/tenants/{id}/apply-pack`): Grocery, Pharmacy, Bakery, Beauty — seeds sample products, fulfilment defaults, welcome message.

### Frontend
- Master Admin wizard now has **3 steps** (Business → Owner → Industry Pack).
- Config drawer per tenant now embeds a live **WhatsApp Simulator** (customer+bot chat bubbles, quick-reply chips).
- All prior modules (client workspace overview/orders/products/inventory/customers/conversations/analytics/settings, fulfilment queue board, master overview/clients/integrations/templates/automations/analytics/audit/settings) still functional.

### Testing
- **iteration_4**: 15/15 new backend tests pass, 14/14 regression still green, 100% frontend flows.
- Test file at `/app/backend/tests/test_commerce_ext.py` (created by testing agent).

## Prioritized backlog
- **P0 (done)**: Master + Client separation, role auth, tenant isolation, fulfilment queues, product/order/inventory CRUD, audit.
- **P1 next**:
  - Real WhatsApp/Meta Cloud API webhook + template send.
  - Cart persistence + abandoned-cart automation execution.
  - Delete-tenant endpoint (currently missing → causes test tenants to pile up).
  - Invoice generation + PDF/WhatsApp delivery.
  - Payment provider webhook (Stripe/Razorpay) + payment verification lifecycle.
  - Extended staff roles (Packer, Delivery, Pickup) with scoped permissions.
- **P2 later**:
  - AI shopping assistant that calls commerce functions (never invents data).
  - Automation event engine execution (rules stored today, not fired).
  - Multi-location pickup, delivery zones by pincode.
  - Platform-level plans & billing.

## Mocked / not-yet-real
- **MOCKED**: WhatsApp/Meta send/receive, payment charging (Stripe test config only), external catalog connectors, automation event execution, template send.
- **PLACEHOLDER**: readiness metrics for onboarding tenants, seeded conversations.

## Next tasks
1. Ship a "Delete tenant" master endpoint for hygiene.
2. Wire Meta Cloud API for actual WhatsApp send + inbound webhook per tenant.
3. Persist WhatsApp cart events → commerce engine → order create with idempotency.
4. Add Stripe test integration and invoice generation.
