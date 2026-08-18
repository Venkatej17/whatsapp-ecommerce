import { useCallback, useEffect, useState } from "react";
import { FileText, Search, Store, Truck, X } from "lucide-react";
import { toast } from "sonner";
import { api, API, humanStatus, money, nextLabel, statusTone } from "../../api";
import Status from "../../components/shared/Status";

export default function Orders({ refresh }) {
  const [list, setList] = useState([]);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("ALL");

  const load = useCallback(() => api.get("/workspace/orders").then((r) => setList(r.data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const filtered = list.filter((o) => (filter === "ALL" || o.fulfilment === filter) && JSON.stringify(o).toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">ORDER OPERATIONS</div>
          <h1>Orders</h1>
          <p>Every WhatsApp cart becomes a structured task here.</p>
        </div>
      </div>
      <div className="toolbar">
        <div className="search"><Search size={17} /><input data-testid="orders-search-input" placeholder="Search order id, customer, phone" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <div className="pill-group" data-testid="orders-filter-group">
          {["ALL", "HOME_DELIVERY", "STORE_PICKUP"].map((k) => (
            <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)} data-testid={`orders-filter-${k}`}>
              {k === "ALL" ? "All" : k === "HOME_DELIVERY" ? <><Truck size={13} /> Delivery</> : <><Store size={13} /> Pickup</>}
            </button>
          ))}
        </div>
      </div>
      <div className="panel full-panel">
        <table>
          <thead><tr><th>ORDER</th><th>CUSTOMER</th><th>FULFILMENT</th><th>PAYMENT</th><th>TOTAL</th><th>STATUS</th><th></th></tr></thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.id} data-testid={`order-row-${o.id}`}>
                <td><b className="mono">{o.id}</b><small>{o.created_at}</small></td>
                <td><b>{o.customer}</b><small>{o.phone}</small></td>
                <td>{o.fulfilment === "STORE_PICKUP" ? "Store pickup" : "Home delivery"}</td>
                <td className={o.payment === "PAID" ? "paid" : "pending"}><b>{o.payment}</b></td>
                <td><b>{money(o.total)}</b></td>
                <td><Status tone={statusTone(o.status)}>{humanStatus(o.status)}</Status></td>
                <td><button className="row-action" data-testid={`open-order-${o.id}`} onClick={() => setSelected(o.id)}>Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected && <OrderDrawer orderId={selected} onClose={() => setSelected(null)} onChange={() => { load(); refresh && refresh(); }} />}
    </section>
  );
}

export function OrderDrawer({ orderId, onClose, onChange }) {
  const [order, setOrder] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(() => api.get(`/workspace/orders/${orderId}`).then((r) => setOrder(r.data)).catch(() => {}), [orderId]);
  useEffect(() => { load(); }, [load]);

  const advance = async () => {
    const step = nextLabel(order);
    if (!step) return;
    setBusy(true);
    try { await api.patch(`/workspace/orders/${orderId}/status`, { status: step.status }); toast.success(`Moved to ${humanStatus(step.status)}`); load(); onChange && onChange(); }
    catch (err) { toast.error(err.response?.data?.detail || "Could not update"); }
    finally { setBusy(false); }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    try { await api.post(`/workspace/orders/${orderId}/notes`, { note, kind: "internal" }); toast.success("Note added"); setNote(""); load(); }
    catch (err) { toast.error("Could not add note"); }
  };

  if (!order) return <div className="modal-backdrop" onClick={onClose}><div className="modal">Loading order…</div></div>;
  const step = nextLabel(order);
  const isPickup = order.fulfilment === "STORE_PICKUP";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()} data-testid="order-drawer">
        <div className="drawer-head">
          <div>
            <div className="eyebrow">ORDER · <span className="mono">{order.id}</span></div>
            <h2>{order.customer}</h2>
            <p>{order.phone} · {order.created_at}</p>
          </div>
          <button className="icon-button" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="drawer-body">
          <div className="order-meta-grid">
            <div><small>FULFILMENT</small><b>{isPickup ? <><Store size={14} /> Store pickup</> : <><Truck size={14} /> Home delivery</>}</b></div>
            <div><small>PAYMENT</small><b className={order.payment === "PAID" ? "paid" : "pending"}>{order.payment}</b></div>
            <div><small>STATUS</small><Status tone={statusTone(order.status)}>{humanStatus(order.status)}</Status></div>
            <div><small>ASSIGNED</small><b>{order.assigned_to || "—"}</b></div>
          </div>

          {isPickup ? (
            <div className="order-address"><small>PICKUP CODE</small><b className="mono">{order.pickup_code}</b></div>
          ) : (
            <div className="order-address"><small>DELIVERY ADDRESS</small><b>{order.address || "—"}</b></div>
          )}

          <div className="picking-list">
            <b>Picking list</b>
            {order.items.map((it, idx) => (
              <div key={idx} className="pick-item" data-testid={`pick-item-${idx}`}>
                <input type="checkbox" defaultChecked={order.status !== "NEW"} />
                <b>{it.name}</b><span className="mono">{it.qty}</span>
              </div>
            ))}
            <div className="order-totals">
              <div><small>Subtotal</small><b>{money(order.subtotal)}</b></div>
              {order.delivery_charge > 0 && <div><small>Delivery</small><b>{money(order.delivery_charge)}</b></div>}
              <div className="grand"><small>Total</small><b>{money(order.total)}</b></div>
            </div>
          </div>

          <div className="timeline">
            <b>Timeline</b>
            {(order.timeline || []).map((t, i) => (
              <div key={i} className="timeline-row"><span className="dot green-dot" /><b>{humanStatus(t.status)}</b><small>{t.at} · {t.by}</small></div>
            ))}
          </div>

          <div className="notes">
            <b>Internal notes</b>
            {(order.internal_notes || []).map((n, i) => <div key={i} className="note-row">💬 {n.note} <small>{n.by}</small></div>)}
            <div className="inline-form">
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note for staff" data-testid="note-input" />
              <button className="outline-button" onClick={addNote} data-testid="add-note-button">Add note</button>
            </div>
          </div>

          <div className="drawer-actions">
            <a className="secondary-button" href={`${API}/workspace/orders/${orderId}/invoice.pdf`} target="_blank" rel="noreferrer" data-testid="download-invoice-button"><FileText size={14} /> Download invoice</a>
            {step && (
              <button className="primary-button" disabled={busy} onClick={advance} data-testid="advance-order-button">
                {busy ? "Updating…" : step.label} →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
