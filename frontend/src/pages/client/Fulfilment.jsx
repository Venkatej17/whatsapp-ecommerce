import { useCallback, useEffect, useState } from "react";
import { Store, Truck } from "lucide-react";
import { toast } from "sonner";
import { api, humanStatus, money, nextLabel, statusTone } from "../../api";
import Status from "../../components/shared/Status";
import { OrderDrawer } from "./Orders";

const COLUMNS = [
  ["NEW", "New orders", "red"],
  ["PICKING", "Picking", "orange"],
  ["PACKING", "Packing", "orange"],
  ["READY_FOR_PICKUP", "Ready for pickup", "blue"],
  ["READY_FOR_DISPATCH", "Ready for dispatch", "blue"],
  ["OUT_FOR_DELIVERY", "Out for delivery", "green"],
  ["COMPLETED", "Completed", "green"],
];

export default function Fulfilment({ refresh }) {
  const [queues, setQueues] = useState({});
  const [selected, setSelected] = useState(null);

  const load = useCallback(() => api.get("/workspace/fulfilment/queues").then((r) => setQueues(r.data)).catch(() => toast.error("Could not load queues")), []);
  useEffect(() => { load(); }, [load]);

  const advance = async (order) => {
    const step = nextLabel(order);
    if (!step) return;
    try { await api.patch(`/workspace/orders/${order.id}/status`, { status: step.status }); toast.success(`Moved to ${humanStatus(step.status)}`); load(); refresh && refresh(); }
    catch (err) { toast.error(err.response?.data?.detail || "Could not update"); }
  };

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">FULFILMENT WORKSPACE</div>
          <h1>Operational queues</h1>
          <p>Move orders through structured steps. Delivery and pickup are handled separately.</p>
        </div>
      </div>
      <div className="queue-board">
        {COLUMNS.map(([key, label, tone]) => {
          const items = queues[key] || [];
          return (
            <div key={key} className="queue-column" data-testid={`queue-${key}`}>
              <div className="queue-header">
                <Status tone={tone}>{label}</Status>
                <b>{items.length}</b>
              </div>
              <div className="queue-items">
                {items.length === 0 && <div className="queue-empty">Nothing here.</div>}
                {items.map((o) => {
                  const step = nextLabel(o);
                  return (
                    <div key={o.id} className="queue-card" data-testid={`queue-card-${o.id}`}>
                      <div className="queue-card-top">
                        <b className="mono">{o.id}</b>
                        {o.fulfilment === "STORE_PICKUP" ? <Store size={13} /> : <Truck size={13} />}
                      </div>
                      <b>{o.customer}</b>
                      <small>{o.items.length} items · {money(o.total)}</small>
                      <div className="queue-card-actions">
                        <button className="row-action" onClick={() => setSelected(o.id)} data-testid={`queue-open-${o.id}`}>Open</button>
                        {step && <button className="row-action primary" onClick={() => advance(o)} data-testid={`queue-advance-${o.id}`}>{step.label} →</button>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      {selected && <OrderDrawer orderId={selected} onClose={() => setSelected(null)} onChange={load} />}
    </section>
  );
}
