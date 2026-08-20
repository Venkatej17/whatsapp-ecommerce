import { BarChart3, CheckCircle2, ClipboardList, Cloud, Package, Plus, Store, Truck } from "lucide-react";
import Metric from "../../components/shared/Metric";
import Status from "../../components/shared/Status";
import { humanStatus, money, statusTone } from "../../api";

export default function Overview({ data, setPage, refresh }) {
  const orders = data.orders || [];
  const t = data.tenant || {};
  const m = data.metrics || {};
  const istHour = Number(
    new Intl.DateTimeFormat("en-US", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(new Date())
  );
  const greeting = istHour < 12 ? "Good morning" : istHour < 17 ? "Good afternoon" : "Good evening";

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow"><span className="pulse" /> LIVE WORKSPACE</div>
          <h1>{greeting}, {t.name || "team"}.</h1>
          <p>Here's the operational pulse for <b>{t.name}</b>.</p>
        </div>
        <div className="heading-actions">
          <button className="secondary-button" data-testid="refresh-dashboard-button" onClick={refresh}><Cloud size={16} /> Sync data</button>
          <button className="primary-button" data-testid="quick-new-product-button" onClick={() => setPage("Products")}><Plus size={17} /> New product</button>
        </div>
      </div>
      <div className="metrics">
        <Metric label="Today's orders" value={m.today_orders} detail={`${m.new_orders} new`} icon={ClipboardList} />
        <Metric label="Revenue today" value={money(m.revenue)} detail="Live workspace" icon={BarChart3} tone="blue" />
        <Metric label="Ready for pickup" value={m.ready_pickup} detail="Awaiting customer" icon={Store} tone="orange" />
        <Metric label="Out for delivery" value={m.out_delivery} detail="Live vehicles" icon={Truck} tone="green" />
      </div>
      <div className="section-grid">
        <section className="panel orders-panel">
          <div className="panel-head">
            <div><h2>Order activity</h2><p>Only your workspace's orders — never mixed with other clients.</p></div>
            <button className="text-button" data-testid="view-all-orders-button" onClick={() => setPage("Orders")}>View all →</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>ORDER</th><th>CUSTOMER</th><th>FULFILMENT</th><th>TOTAL</th><th>STATUS</th></tr></thead>
              <tbody>
                {orders.slice(0, 5).map((o) => (
                  <tr key={o.id} data-testid={`order-row-${o.id}`}>
                    <td><b className="mono">{o.id}</b><small>{o.created_at}</small></td>
                    <td><b>{o.customer}</b><small>{o.phone}</small></td>
                    <td>{o.fulfilment === "STORE_PICKUP" ? <span className="fulfilment"><Store size={13} /> Store pickup</span> : <span className="fulfilment"><Truck size={13} /> Home delivery</span>}</td>
                    <td><b>{money(o.total)}</b><small className={o.payment === "PAID" ? "paid" : "pending"}>{o.payment}</small></td>
                    <td><Status tone={statusTone(o.status)}>{humanStatus(o.status)}</Status></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel onboarding">
          <div className="panel-head">
            <div><h2>Workspace readiness</h2><p>Configuration handled by the platform team.</p></div>
            <span className="readiness">{t.health ?? 0}%</span>
          </div>
          <div className="progress"><span style={{ width: `${t.health ?? 0}%` }} /></div>
          <div className="checklist">
            {[
              ["Business profile", true],
              ["Owner login", true],
              ["WhatsApp connected", t.integrations?.whatsapp?.connected],
              ["Catalog connected", t.integrations?.catalog?.connected],
              ["Payment configured", t.integrations?.payment?.configured],
              ["Fulfilment configured", t.onboarding?.fulfilment_configured],
            ].map(([label, done]) => (
              <div key={label} className={done ? "done" : ""}>
                <CheckCircle2 size={15} color={done ? "#c2410c" : "#94a3b8"} />
                <b>{label}</b><small>{done ? "Configured" : "Ask platform team"}</small>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="bottom-grid">
        <section className="panel">
          <div className="panel-head"><div><h2>Inventory watchlist</h2><p>Refresh stock daily to prevent oversell.</p></div><button className="text-button" onClick={() => setPage("Inventory")}>Open inventory →</button></div>
          <div className="inventory-panel">
            {(data.products || []).filter((p) => p.stock < 20).slice(0, 6).map((p) => (
              <div className="stock-row" key={p.id} data-testid={`watch-${p.id}`}>
                <div className="product-symbol"><Package size={14} /></div>
                <div><b>{p.name}</b><small>{p.category}</small></div>
                <div className="stock-meter"><span style={{ width: `${Math.min(100, (p.stock / 50) * 100)}%` }} /></div>
                <strong>{p.stock} <small>units</small></strong>
                <Status tone={p.stock === 0 ? "red" : "orange"}>{p.status}</Status>
              </div>
            ))}
            {(data.products || []).filter((p) => p.stock < 20).length === 0 && (
              <div className="empty-inline">All stock is healthy today.</div>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Fulfilment quick actions</h2><p>Route from here into structured queues.</p></div></div>
          <div className="action-grid">
            <button data-testid="qa-orders" onClick={() => setPage("Orders")}><b>Open order queue</b><small>Pick, pack, dispatch.</small></button>
            <button data-testid="qa-fulfilment" onClick={() => setPage("Fulfilment")}><b>Fulfilment board</b><small>New → Picking → Ready.</small></button>
            <button data-testid="qa-customers" onClick={() => setPage("Customers")}><b>Customer CRM</b><small>Tags, orders, spend.</small></button>
            <button data-testid="qa-conversations" onClick={() => setPage("Conversations")}><b>WhatsApp threads</b><small>Linked to each order.</small></button>
          </div>
        </section>
      </div>
    </section>
  );
}
