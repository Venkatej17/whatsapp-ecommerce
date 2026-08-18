import { useEffect, useState } from "react";
import { BarChart3, Package, ShoppingBag, Store, Truck } from "lucide-react";
import { api, money } from "../../api";
import Metric from "../../components/shared/Metric";

export default function Analytics() {
  const [data, setData] = useState({ totals: {}, top_products: [], recent_orders: [] });
  useEffect(() => { api.get("/workspace/analytics").then((r) => setData(r.data)).catch(() => {}); }, []);
  const t = data.totals || {};
  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE ANALYTICS</div>
          <h1>Business performance</h1>
          <p>Only your workspace's data — never mixed with other clients.</p>
        </div>
      </div>
      <div className="metrics">
        <Metric label="Orders" value={t.orders} detail="All time" icon={ShoppingBag} />
        <Metric label="Revenue" value={money(t.revenue)} detail={`Avg ${money(t.avg_order)}`} icon={BarChart3} tone="blue" />
        <Metric label="Home delivery" value={t.delivery_orders} detail={money(t.delivery_revenue) + " delivery fees"} icon={Truck} tone="green" />
        <Metric label="Store pickup" value={t.pickup_orders} detail="Walk-in fulfilment" icon={Store} tone="orange" />
      </div>
      <div className="section-grid">
        <div className="panel">
          <div className="panel-head"><div><h2>Top products by stock</h2><p>Healthy inventory drives repeat sales.</p></div></div>
          <div className="inventory-panel">
            {data.top_products.map((p) => (
              <div className="stock-row" key={p.id}>
                <div className="product-symbol"><Package size={14} /></div>
                <div><b>{p.name}</b><small>{p.category}</small></div>
                <div className="stock-meter"><span style={{ width: `${Math.min(100, (p.stock / 60) * 100)}%` }} /></div>
                <strong>{p.stock} <small>units</small></strong>
                <small>{money(p.price)}</small>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><div><h2>Recent orders</h2><p>Latest {data.recent_orders.length} orders.</p></div></div>
          <div className="inventory-panel">
            {data.recent_orders.map((o) => (
              <div key={o.id} className="stock-row" style={{ gridTemplateColumns: "1fr 90px 80px" }}>
                <div><b className="mono">{o.id}</b><small>{o.customer}</small></div>
                <b>{money(o.total)}</b>
                <small>{o.status}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
